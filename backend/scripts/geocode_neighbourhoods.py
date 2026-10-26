#!/usr/bin/env python3
"""
DineMate — One-Time Nominatim Neighbourhood Geocoder.
Phase 3 / Step 1.1: Offline Geocoding & Coordinate Dataset Creation.

Reference: docs/geo_proximity_plan.md §3, §4, §10

Responsibilities:
1. Query distinct Bangalore neighbourhoods from the SQLite catalog database.
2. Query OpenStreetMap Nominatim with strict rate limiting (>= 1.0s between requests)
   and a custom descriptive User-Agent.
3. Validate returned coordinates against the Bangalore bounding box (12.7–13.2°N, 77.4–77.9°E).
4. Flag broad regional zones ("Central Bangalore", "East Bangalore", "West Bangalore",
   "North Bangalore", "South Bangalore") with broad_area: True, verified: False.
5. Flag ambiguous localities (e.g., BTM, HSR, Koramangala) with verified: False
   for inspection and centroid verification (Step 1.2).
6. Never invent coordinates: unverified/missing locations have lat: None, lng: None.
7. Save results to data/processed/neighbourhood_coords.json following the schema in §4.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

import httpx

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dinemate_geocoder")

# ============================================================================
# Constants & Configuration
# ============================================================================

SCHEMA_VERSION = "1.0"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "DineMate-Bangalore-Geocoder/1.0 (dinemate-app@local)"

# Strict bounding box for Bangalore metropolitan area (docs/geo_proximity_plan.md §2, §3)
BBOX_LAT_MIN = 12.7
BBOX_LAT_MAX = 13.2
BBOX_LNG_MIN = 77.4
BBOX_LNG_MAX = 77.9

# 5 broad non-specific regional zones (plan §2.4, §10.1)
# These must have broad_area: True and verified: False to inhibit automatic radius matching
BROAD_AREAS = {
    "Central Bangalore",
    "East Bangalore",
    "West Bangalore",
    "North Bangalore",
    "South Bangalore",
}

# Ambiguous localities (acronyms or multi-block areas) that require
# manual centroid verification in Step 1.2 (plan §10.1, §10.2).
# BTM, HSR, and Koramangala centroids have now been verified against OSM Nominatim.
AMBIGUOUS_AREAS: set[str] = set()

# Targeted query aliases to assist Nominatim search precision without inventing coordinates
QUERY_ALIASES: dict[str, str] = {
    "BTM": "BTM Layout",
    "HSR": "HSR Layout",
    "KR Puram": "Krishnarajapuram",
    "ITPL Main Road, Whitefield": "Park Square Mall, Whitefield",
    "Varthur Main Road, Whitefield": "Varthur Main Road Whitefield",
    "Vijay Nagar": "Vijayanagar",
    "Sanjay Nagar": "Sanjaynagar",
    "Thippasandra": "New Thippasandra",
    "Rammurthy Nagar": "Ramamurthy Nagar",
    "Sadashiv Nagar": "Sadashivanagar",
}


# ============================================================================
# Helpers & Rate Limiter
# ============================================================================

class StrictRateLimiter:
    """
    Enforces a strict minimum delay between consecutive network calls
    to comply with OpenStreetMap Nominatim Usage Policy.
    """

    def __init__(self, min_interval_seconds: float = 1.05) -> None:
        self.min_interval = max(min_interval_seconds, 1.0)
        self.last_request_time: float = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            sleep_needed = self.min_interval - elapsed
            time.sleep(sleep_needed)
        self.last_request_time = time.monotonic()


def is_within_bangalore_bbox(lat: float, lng: float) -> bool:
    """Verify if decimal coordinates fall inside the defined Bangalore bounding box."""
    return (
        BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX
        and BBOX_LNG_MIN <= lng <= BBOX_LNG_MAX
    )


def resolve_project_root() -> Path:
    """Resolve repository root directory relative to this script."""
    # This script is located at backend/scripts/geocode_neighbourhoods.py
    return Path(__file__).resolve().parents[2]


def load_neighbourhoods_from_db(db_path: Path) -> list[str]:
    """
    Read distinct neighbourhoods from the SQLite catalog database.
    Checks `locations` table first, then falls back to `restaurants` table.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite database not found at {db_path}. "
            "Ensure data ingestion has run (`python -m app.catalog.ingest`)."
        )

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        # Check locations table first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='locations';")
        if cursor.fetchone():
            cursor.execute(
                "SELECT neighborhood FROM locations WHERE neighborhood IS NOT NULL AND neighborhood != '' ORDER BY neighborhood;"
            )
            rows = cursor.fetchall()
            if rows:
                return [r[0].strip() for r in rows if r[0] and r[0].strip()]

        # Fallback to restaurants table
        cursor.execute(
            "SELECT DISTINCT neighborhood FROM restaurants WHERE neighborhood IS NOT NULL AND neighborhood != '' ORDER BY neighborhood;"
        )
        return [r[0].strip() for r in cursor.fetchall() if r[0] and r[0].strip()]


def load_existing_coords(output_file: Path) -> dict[str, Any]:
    """Load existing coordinate lookup file if present, for incremental resumption."""
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Could not parse existing coords file %s: %s", output_file, e)
    return {"__version__": SCHEMA_VERSION}


def save_coords(output_file: Path, coords_data: dict[str, Any]) -> None:
    """
    Persist coordinates to JSON file with __version__ at root,
    sorted alphabetically by neighbourhood name.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Ensure version is preserved and entries are sorted alphabetically
    version = coords_data.get("__version__", SCHEMA_VERSION)
    entries = {k: v for k, v in coords_data.items() if k != "__version__"}
    sorted_entries = dict(sorted(entries.items(), key=lambda item: item[0].lower()))

    payload = {"__version__": version, **sorted_entries}

    temp_file = output_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    temp_file.replace(output_file)
    logger.info("Saved %d neighbourhoods to %s", len(sorted_entries), output_file)


# ============================================================================
# Nominatim Geocoding Client
# ============================================================================

def query_nominatim(
    client: httpx.Client,
    rate_limiter: StrictRateLimiter,
    neighbourhood: str,
    max_retries: int = 3,
) -> tuple[float | None, float | None, str | None]:
    """
    Query OpenStreetMap Nominatim for a single neighbourhood.

    Returns:
        tuple[lat, lng, error_message]
        Coordinates are rounded to 4 decimal places, or (None, None) if not found/invalid.
        Never invents coordinates.
    """
    search_term = QUERY_ALIASES.get(neighbourhood, neighbourhood)
    query_str = f"{search_term}, Bengaluru, Karnataka, India"
    params = {
        "q": query_str,
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
    }

    for attempt in range(1, max_retries + 1):
        rate_limiter.wait()
        try:
            response = client.get(NOMINATIM_SEARCH_URL, params=params)

            if response.status_code == 429:
                wait_time = 5.0 * attempt
                logger.warning(
                    "Received HTTP 429 (Rate limit). Backing off for %.1fs (attempt %d/%d)...",
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            results = response.json()

            if not results or not isinstance(results, list):
                logger.warning("No Nominatim results found for query: %r", query_str)
                return None, None, "No results returned by Nominatim"

            item = results[0]
            lat_raw = item.get("lat")
            lon_raw = item.get("lon")
            if lat_raw is None or lon_raw is None:
                return None, None, "Missing lat/lon in Nominatim result"

            lat = round(float(lat_raw), 4)
            lng = round(float(lon_raw), 4)

            # Strict Bangalore bounding box validation
            if not is_within_bangalore_bbox(lat, lng):
                logger.warning(
                    "Coordinates (%.4f, %.4f) for '%s' fall outside Bangalore bounding box [%.1f–%.1f, %.1f–%.1f]. Discarding.",
                    lat,
                    lng,
                    neighbourhood,
                    BBOX_LAT_MIN,
                    BBOX_LAT_MAX,
                    BBOX_LNG_MIN,
                    BBOX_LNG_MAX,
                )
                return None, None, f"Coordinates ({lat}, {lng}) outside Bangalore bounding box"

            return lat, lng, None

        except httpx.HTTPError as exc:
            logger.warning(
                "HTTP error geocoding '%s' (attempt %d/%d): %s",
                neighbourhood,
                attempt,
                max_retries,
                exc,
            )
            if attempt == max_retries:
                return None, None, str(exc)
            time.sleep(2.0 * attempt)

        except Exception as exc:
            logger.error("Unexpected error geocoding '%s': %s", neighbourhood, exc)
            return None, None, str(exc)

    return None, None, "Max retries exceeded"


# ============================================================================
# Batch Geocoder Engine
# ============================================================================

def build_entry(
    neighbourhood: str,
    lat: float | None,
    lng: float | None,
) -> dict[str, Any]:
    """
    Construct coordinate entry dictionary adhering to the schema:
    - broad_area: True for the 5 non-specific regional zones
    - verified: False for broad areas, ambiguous areas, or missing coordinates.
                True for valid non-ambiguous coordinates within bounding box.
    """
    is_broad = neighbourhood in BROAD_AREAS
    is_ambiguous = neighbourhood in AMBIGUOUS_AREAS

    if lat is None or lng is None:
        verified = False
    elif is_broad:
        verified = False
    elif is_ambiguous:
        # Flagged for manual centroid verification in Step 1.2
        verified = False
    else:
        verified = True

    return {
        "lat": lat,
        "lng": lng,
        "verified": verified,
        "broad_area": is_broad,
    }


def run_geocoding(
    db_path: Path,
    output_path: Path,
    delay_seconds: float = 1.05,
    force_all: bool = False,
    dry_run: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
) -> None:
    """
    Main orchestration function for offline neighbourhood geocoding.
    """
    neighbourhoods = load_neighbourhoods_from_db(db_path)
    logger.info("Found %d distinct neighbourhoods in database.", len(neighbourhoods))

    if dry_run:
        logger.info("[DRY RUN] Simulating geocoder without making any network requests:")
        for idx, name in enumerate(neighbourhoods, 1):
            is_broad = name in BROAD_AREAS
            is_ambiguous = name in AMBIGUOUS_AREAS
            alias = QUERY_ALIASES.get(name)
            flags = []
            if is_broad:
                flags.append("BROAD_AREA")
            if is_ambiguous:
                flags.append("AMBIGUOUS (needs Step 1.2 verification)")
            if alias:
                flags.append(f"alias: '{alias}'")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {idx:2d}. {name:<32}{flag_str}")
        print(f"\nTotal: {len(neighbourhoods)} neighbourhoods. Dry run completed successfully.")
        return

    coords_data = load_existing_coords(output_path)
    rate_limiter = StrictRateLimiter(min_interval_seconds=delay_seconds)

    # Determine which neighbourhoods need geocoding
    to_process: list[str] = []
    for name in neighbourhoods:
        if force_all or name not in coords_data:
            to_process.append(name)
        elif not coords_data[name].get("verified", False) and coords_data[name].get("lat") is None:
            # Retry previously failed unverified entries without coordinates
            to_process.append(name)

    logger.info(
        "Processing %d neighbourhoods (%d already cached). Rate limit: %.2fs delay between requests.",
        len(to_process),
        len(neighbourhoods) - len(to_process),
        rate_limiter.min_interval,
    )

    if not to_process:
        logger.info("All neighbourhoods already geocoded. Use --force to re-geocode.")
        return

    client_headers = {"User-Agent": user_agent}

    try:
        with httpx.Client(headers=client_headers, timeout=12.0) as client:
            for idx, name in enumerate(to_process, 1):
                logger.info(
                    "[%d/%d] Geocoding '%s'...",
                    idx,
                    len(to_process),
                    name,
                )

                lat, lng, err = query_nominatim(client, rate_limiter, name)

                if err:
                    logger.warning("  -> Geocoding result for '%s': FAILED (%s)", name, err)
                else:
                    logger.info("  -> Geocoding result for '%s': lat=%.4f, lng=%.4f", name, lat, lng)

                entry = build_entry(name, lat, lng)
                coords_data[name] = entry

                # Checkpoint save every 10 queries
                if idx % 10 == 0:
                    save_coords(output_path, coords_data)

    except KeyboardInterrupt:
        logger.warning("\nExecution interrupted by user. Saving completed progress...")
    finally:
        save_coords(output_path, coords_data)


# ============================================================================
# CLI Interface
# ============================================================================

def parse_args() -> argparse.Namespace:
    project_root = resolve_project_root()
    default_db = project_root / "data" / "processed" / "restaurants.sqlite"
    default_out = project_root / "data" / "processed" / "neighbourhood_coords.json"

    parser = argparse.ArgumentParser(
        description="One-time OpenStreetMap Nominatim geocoder for DineMate Bangalore neighbourhoods.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db,
        help="Path to SQLite catalog database containing the 'locations' table.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_out,
        help="Path to output JSON file to store coordinates.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.05,
        help="Delay in seconds between Nominatim requests (must be >= 1.0s).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-geocoding of all neighbourhoods even if already present in output file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution: read neighbourhoods from DB and display query plan without making network requests.",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=DEFAULT_USER_AGENT,
        help="Custom User-Agent header for Nominatim requests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.delay < 1.0:
        logger.error("Rate limit delay cannot be less than 1.0s per OpenStreetMap Nominatim policy.")
        sys.exit(1)

    try:
        run_geocoding(
            db_path=args.db_path,
            output_path=args.output,
            delay_seconds=args.delay,
            force_all=args.force,
            dry_run=args.dry_run,
            user_agent=args.user_agent,
        )
    except Exception as exc:
        logger.critical("Fatal error during geocoding: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

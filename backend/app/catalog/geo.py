"""
Core Geo Engine Module (Phase 3 / Step 2).
Provides coordinate loading, bounding box validation, pure-Python Haversine distance
calculation, and nearby-neighbourhood proximity search.

Reference: docs/geo_proximity_plan.md §2, §4, §5, §10
"""

from __future__ import annotations

from functools import lru_cache
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bounding box for valid Bangalore metropolitan coordinates
BBOX_LAT_MIN = 12.7
BBOX_LAT_MAX = 13.2
BBOX_LNG_MIN = 77.4
BBOX_LNG_MAX = 77.9

# Earth radius in kilometers for Haversine calculation
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Compute great-circle distance between two points on Earth using pure-Python Haversine formula.

    Formula reference: docs/geo_proximity_plan.md §5
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_in_bangalore_bbox(lat: float, lng: float) -> bool:
    """Validate if coordinates fall inside the defined Bangalore bounding box."""
    return (
        BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX
        and BBOX_LNG_MIN <= lng <= BBOX_LNG_MAX
    )


def get_default_coords_path() -> Path:
    """Resolve the default path to data/processed/neighbourhood_coords.json."""
    env_path = os.getenv("NEIGHBOURHOOD_COORDS_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_absolute():
            return p
        root_dir = Path(__file__).resolve().parents[3]
        return root_dir / env_path

    # Default: relative to repository root
    root_dir = Path(__file__).resolve().parents[3]
    return root_dir / "data" / "processed" / "neighbourhood_coords.json"


@lru_cache(maxsize=16)
def load_raw_coords(coords_path_str: str | None = None) -> dict[str, Any]:
    """
    Load raw JSON coordinates lookup dictionary with in-memory caching.
    """
    path = Path(coords_path_str) if coords_path_str else get_default_coords_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Neighbourhood coordinates file not found at: {path}. "
            "Please run `python backend/scripts/geocode_neighbourhoods.py` first."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid format in coordinates file {path}: expected dict.")

    # Exclude root metadata fields like '__version__'
    return {k: v for k, v in data.items() if not k.startswith("__")}


@lru_cache(maxsize=16)
def load_coords(coords_path_str: str | None = None) -> dict[str, dict[str, float]]:
    """
    Load and return verified, non-broad-area neighbourhood coordinates.

    Gating rules (plan §2.2, §2.4, §10.2):
    - verified MUST be True
    - broad_area MUST NOT be True
    - lat and lng MUST NOT be None
    - lat and lng MUST fall inside the Bangalore bounding box (12.7–13.2°N, 77.4–77.9°E)

    Returns:
        Dict mapping canonical neighbourhood name -> {"lat": float, "lng": float}
    """
    raw_data = load_raw_coords(coords_path_str)
    verified_coords: dict[str, dict[str, float]] = {}

    for name, info in raw_data.items():
        if not isinstance(info, dict):
            continue

        # Strict verification and broad-area exclusions
        if not info.get("verified", False):
            continue
        if info.get("broad_area", False):
            continue

        lat = info.get("lat")
        lng = info.get("lng")
        if lat is None or lng is None:
            continue

        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (ValueError, TypeError):
            continue

        if not is_in_bangalore_bbox(lat_f, lng_f):
            logger.warning(
                "Coordinate for '%s' (%.4f, %.4f) outside Bangalore bounding box; excluded from verified coords.",
                name,
                lat_f,
                lng_f,
            )
            continue

        verified_coords[name] = {"lat": lat_f, "lng": lng_f}

    return verified_coords


def find_nearby_neighbourhoods_with_distance(
    query_location: str,
    radius_km: float,
    coords_path_str: str | None = None,
) -> list[tuple[str, float]]:
    """
    Find neighbouring locations within `radius_km` of `query_location`, sorted by distance.

    Returns:
        List of tuples: (neighbourhood_name, distance_in_km)
        Empty list if query_location is unverified, missing, a broad area, or radius <= 0.
    """
    if not query_location or radius_km <= 0:
        return []

    # Check verified coords lookup
    coords = load_coords(coords_path_str)

    # Case-insensitive lookup for query_location
    query_norm = query_location.strip().lower()
    matched_canonical = None
    query_point = None

    for name, pt in coords.items():
        if name.lower() == query_norm:
            matched_canonical = name
            query_point = pt
            break

    # If query location is not in verified coords (unverified, broad area, or unknown), return []
    if query_point is None or matched_canonical is None:
        return []

    results: list[tuple[str, float]] = []
    q_lat, q_lng = query_point["lat"], query_point["lng"]

    for name, pt in coords.items():
        # Exclude the query location itself
        if name.lower() == query_norm:
            continue

        dist = haversine_km(q_lat, q_lng, pt["lat"], pt["lng"])
        if dist <= radius_km:
            results.append((name, round(dist, 3)))

    # Sort ascending by distance (closest first)
    results.sort(key=lambda item: item[1])
    return results


def find_nearby_neighbourhoods(
    query_location: str,
    radius_km: float,
    coords_path_str: str | None = None,
) -> list[str]:
    """
    Find neighbouring location names within `radius_km` of `query_location` (excluding query location).

    Reference: docs/geo_proximity_plan.md §5, §10.2
    - Returns [] if query_location is unverified, missing, or broad_area.
    - Returns [] if radius_km <= 0.
    """
    nearby_with_dist = find_nearby_neighbourhoods_with_distance(
        query_location=query_location,
        radius_km=radius_km,
        coords_path_str=coords_path_str,
    )
    return [name for name, _ in nearby_with_dist]


def clear_geo_cache() -> None:
    """Clear in-memory LRU caches for coordinate lookups."""
    load_raw_coords.cache_clear()
    load_coords.cache_clear()

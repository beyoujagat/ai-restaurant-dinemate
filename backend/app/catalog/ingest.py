"""
DineMate Catalog Ingestion Pipeline (Phase 1).

Loads the Zomato Bangalore dataset from Hugging Face, cleans and normalizes
ratings, costs, cuisines, and reviews, deduplicates listings on (name, address),
and persists the catalog to SQLite and Parquet.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _is_empty(val: Any) -> bool:
    """Helper to check for None, empty, or NaN without requiring pandas at module load."""
    if val is None:
        return True
    if isinstance(val, float) and val != val:  # math.isnan check
        return True
    return False

# Allowed columns to keep from Hugging Face dataset (phone and menu_item are dropped)
RAW_COLUMNS_TO_KEEP = [
    "name",
    "address",
    "location",
    "listed_in(city)",
    "cuisines",
    "approx_cost(for two people)",
    "rate",
    "votes",
    "rest_type",
    "listed_in(type)",
    "online_order",
    "book_table",
    "dish_liked",
    "reviews_list",
    "url",
]


# ============================================================================
# Field Parsers
# ============================================================================

def parse_rate(val: Any) -> float | None:
    """
    Parse a rating string to float in range [0.0, 5.0].
    Examples:
      "4.1/5" -> 4.1
      "NEW", "-", "", None -> None
      "3.8" -> 3.8
    """
    if _is_empty(val):
        return None

    s = str(val).strip()
    if not s or s.upper() in {"NEW", "-", "NAN", "NONE"}:
        return None

    # Handle "4.1/5" or "4.1 / 5"
    if "/" in s:
        s = s.split("/")[0].strip()

    try:
        score = float(s)
        if 0.0 <= score <= 5.0:
            return round(score, 1)
        return None
    except (ValueError, TypeError):
        return None


def parse_cost(val: Any) -> int | None:
    """
    Parse approx_cost(for two people) into integer INR amount.
    Examples:
      "800" -> 800
      "1,200" -> 1200
      missing / "-" -> None
    """
    if _is_empty(val):
        return None

    if isinstance(val, (int, float)):
        return int(val) if val > 0 else None

    s = str(val).strip().replace(",", "")
    if not s or s.upper() in {"-", "NAN", "NONE"}:
        return None

    try:
        # Handle cases like "1200.0"
        cost = int(float(s))
        return cost if cost > 0 else None
    except (ValueError, TypeError):
        return None


def parse_cuisines(val: Any) -> list[str]:
    """
    Parse comma-separated cuisines into trimmed list.
    Examples:
      "North Indian, Mughlai, Chinese" -> ["North Indian", "Mughlai", "Chinese"]
    """
    if _is_empty(val):
        return []

    s = str(val).strip()
    if not s:
        return []

    items = [c.strip() for c in s.split(",") if c.strip()]
    # Preserve order while deduplicating case-insensitively
    seen = set()
    result = []
    for item in items:
        norm = item.lower()
        if norm not in seen:
            seen.add(norm)
            result.append(item)
    return result


def parse_votes(val: Any) -> int:
    """
    Parse votes column into non-negative integer.
    """
    if _is_empty(val):
        return 0

    if isinstance(val, (int, float)):
        return max(0, int(val))

    s = str(val).strip().replace(",", "")
    try:
        return max(0, int(float(s)))
    except (ValueError, TypeError):
        return 0


def parse_bool(val: Any) -> bool:
    """
    Parse yes/no boolean indicators.
    """
    if _is_empty(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {"yes", "y", "true", "1"}


def parse_list_field(val: Any) -> list[str]:
    """
    Split comma-separated strings (like rest_type, dish_liked) into cleaned string list.
    """
    if _is_empty(val):
        return []

    s = str(val).strip()
    if not s:
        return []

    items = [item.strip() for item in s.split(",") if item.strip()]
    seen = set()
    result = []
    for item in items:
        norm = item.lower()
        if norm not in seen:
            seen.add(norm)
            result.append(item)
    return result


def parse_review_snippets(val: Any, max_snippets: int = 3, max_chars: int = 200) -> list[str]:
    """
    Extract up to `max_snippets` short review snippets from the raw reviews_list string.
    Does not evaluate whole string if very large; extracts with regex and cleans prefixes.
    """
    if _is_empty(val):
        return []

    s = str(val).strip()
    if not s or s == "[]":
        return []

    snippets: list[str] = []

    # First attempt regex to extract after RATED\n
    pattern = r"RATED\\+n\s*(.*?)(?=(?:'[\s,\)\]]|\"[\s,\)\]]|\\n\s*RATED|\Z))"
    raw_matches = re.findall(pattern, s, re.DOTALL)

    if not raw_matches:
        # Fallback to ast.literal_eval for small strings
        if len(s) < 2000 and s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, tuple) and len(item) >= 2:
                            text = str(item[1]).replace("RATED\n", "").strip()
                            if text:
                                raw_matches.append(text)
            except Exception:
                pass

    for match in raw_matches:
        cleaned = re.sub(r"\s+", " ", match).strip()
        cleaned = cleaned.replace("\\n", " ").replace("\\'", "'").replace('\\"', '"')
        # Remove trailing or leading quotes
        cleaned = cleaned.strip("\"' \t\r\n")
        if len(cleaned) < 10:
            continue

        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rsplit(" ", 1)[0] + "..."

        if cleaned not in snippets:
            snippets.append(cleaned)
            if len(snippets) >= max_snippets:
                break

    return snippets


def generate_restaurant_id(name: str, address: str) -> str:
    """
    Deterministic 16-character hex ID based on normalized (name + address).
    """
    norm_name = re.sub(r"\s+", " ", (name or "").strip().lower())
    norm_address = re.sub(r"\s+", " ", (address or "").strip().lower())
    key = f"{norm_name}::{norm_address}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:16]


# ============================================================================
# Deduplication and Cleaning
# ============================================================================

def clean_and_deduplicate(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Clean raw records, drop rows without a valid restaurant name, and deduplicate
    on normalized (name, address), aggregating rest_type and listed_in(type) lists.
    """
    row_count_in = 0
    empty_name_count = 0
    grouped: dict[str, dict[str, Any]] = {}

    for row in records:
        row_count_in += 1

        raw_name = row.get("name")
        if _is_empty(raw_name):
            empty_name_count += 1
            continue

        name = str(raw_name).strip()
        if not name:
            empty_name_count += 1
            continue

        address = str(row.get("address") or "").strip()
        rest_id = generate_restaurant_id(name, address)

        # Parse fields for current row
        neighborhood = str(row.get("location") or "").strip()
        listed_city = str(row.get("listed_in(city)") or "").strip()
        cuisines_list = parse_cuisines(row.get("cuisines"))
        cost = parse_cost(row.get("approx_cost(for two people)"))
        rating = parse_rate(row.get("rate"))
        votes = parse_votes(row.get("votes"))
        online_order = parse_bool(row.get("online_order"))
        book_table = parse_bool(row.get("book_table"))
        rest_types = parse_list_field(row.get("rest_type"))
        listed_type = str(row.get("listed_in(type)") or "").strip()
        dishes = parse_list_field(row.get("dish_liked"))
        review_snippets = parse_review_snippets(row.get("reviews_list"))
        url = str(row.get("url") or "").strip() or None

        if rest_id not in grouped:
            grouped[rest_id] = {
                "id": rest_id,
                "name": name,
                "address": address,
                "neighborhood": neighborhood,
                "listed_city": listed_city,
                "cuisines": cuisines_list,
                "cost_for_two": cost,
                "rating": rating,
                "votes": votes,
                "online_order": online_order,
                "book_table": book_table,
                "rest_types": set(rest_types),
                "listed_types": {listed_type} if listed_type else set(),
                "dishes_liked": set(dishes),
                "review_snippets": review_snippets,
                "url": url,
            }
        else:
            # Merge with existing listing
            entry = grouped[rest_id]
            # Accumulate types and dishes
            entry["rest_types"].update(rest_types)
            if listed_type:
                entry["listed_types"].add(listed_type)
            entry["dishes_liked"].update(dishes)

            # Preserve highest votes and corresponding rating
            if votes > entry["votes"]:
                entry["votes"] = votes
                if rating is not None:
                    entry["rating"] = rating

            # Fill rating / cost if previously missing
            if entry["rating"] is None and rating is not None:
                entry["rating"] = rating
            if entry["cost_for_two"] is None and cost is not None:
                entry["cost_for_two"] = cost

            # Merge flags (if true anywhere, true)
            entry["online_order"] = entry["online_order"] or online_order
            entry["book_table"] = entry["book_table"] or book_table

            # Preserve location if missing
            if not entry["neighborhood"] and neighborhood:
                entry["neighborhood"] = neighborhood
            if not entry["listed_city"] and listed_city:
                entry["listed_city"] = listed_city

            # If review snippets were empty, populate
            if not entry["review_snippets"] and review_snippets:
                entry["review_snippets"] = review_snippets

            # Merge cuisines
            for c in cuisines_list:
                if c not in entry["cuisines"]:
                    entry["cuisines"].append(c)

    # Convert sets to sorted lists for serialization
    cleaned_records: list[dict[str, Any]] = []
    distinct_neighborhoods: set[str] = set()
    distinct_cuisines: set[str] = set()

    for item in grouped.values():
        item["rest_types"] = sorted(item["rest_types"])
        item["listed_types"] = sorted(item["listed_types"])
        item["dishes_liked"] = sorted(item["dishes_liked"])
        item["cuisines_raw"] = ", ".join(item["cuisines"])

        if item["neighborhood"]:
            distinct_neighborhoods.add(item["neighborhood"])
        for c in item["cuisines"]:
            distinct_cuisines.add(c)

        cleaned_records.append(item)

    stats = {
        "row_count_in": row_count_in,
        "empty_name_dropped": empty_name_count,
        "row_count_out": len(cleaned_records),
        "distinct_neighborhoods": len(distinct_neighborhoods),
        "distinct_cuisines": len(distinct_cuisines),
    }

    return cleaned_records, stats


# ============================================================================
# SQLite and Parquet Persistence
# ============================================================================

def save_to_sqlite(records: list[dict[str, Any]], sqlite_path: Path | str) -> None:
    """
    Persist cleaned records to SQLite with indices and facet tables.
    """
    path = Path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Connect to SQLite
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    # Drop existing tables
    cursor.execute("DROP TABLE IF EXISTS restaurant_cuisine;")
    cursor.execute("DROP TABLE IF EXISTS locations;")
    cursor.execute("DROP TABLE IF EXISTS cuisines;")
    cursor.execute("DROP TABLE IF EXISTS restaurants;")

    # Create canonical restaurants table
    cursor.execute("""
        CREATE TABLE restaurants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            neighborhood TEXT,
            listed_city TEXT,
            cuisines TEXT,             -- JSON string array
            cuisines_raw TEXT,         -- comma-separated string for fast LIKE
            cost_for_two INTEGER,
            rating REAL,
            votes INTEGER DEFAULT 0,
            rest_types TEXT,           -- JSON string array
            listed_types TEXT,         -- JSON string array
            online_order INTEGER DEFAULT 0,
            book_table INTEGER DEFAULT 0,
            dishes_liked TEXT,         -- JSON string array
            review_snippets TEXT,      -- JSON string array
            url TEXT
        );
    """)

    # Create restaurant_cuisine junction table for fast indexed cuisine queries
    cursor.execute("""
        CREATE TABLE restaurant_cuisine (
            restaurant_id TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            PRIMARY KEY (restaurant_id, cuisine),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        );
    """)

    # Create locations facet table
    cursor.execute("""
        CREATE TABLE locations (
            neighborhood TEXT PRIMARY KEY
        );
    """)

    # Create cuisines facet table
    cursor.execute("""
        CREATE TABLE cuisines (
            cuisine TEXT PRIMARY KEY
        );
    """)

    # Prepare bulk insertions
    restaurant_rows = []
    cuisine_rows = set()
    distinct_locs = set()
    distinct_cuis = set()

    for r in records:
        restaurant_rows.append((
            r["id"],
            r["name"],
            r["address"],
            r["neighborhood"],
            r["listed_city"],
            json.dumps(r["cuisines"]),
            r["cuisines_raw"],
            r["cost_for_two"],
            r["rating"],
            r["votes"],
            json.dumps(r["rest_types"]),
            json.dumps(r["listed_types"]),
            1 if r["online_order"] else 0,
            1 if r["book_table"] else 0,
            json.dumps(r["dishes_liked"]),
            json.dumps(r["review_snippets"]),
            r["url"],
        ))

        if r["neighborhood"]:
            distinct_locs.add((r["neighborhood"],))

        for c in r["cuisines"]:
            cuisine_rows.add((r["id"], c))
            distinct_cuis.add((c,))

    cursor.executemany("""
        INSERT INTO restaurants (
            id, name, address, neighborhood, listed_city, cuisines, cuisines_raw,
            cost_for_two, rating, votes, rest_types, listed_types, online_order,
            book_table, dishes_liked, review_snippets, url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, restaurant_rows)

    cursor.executemany("""
        INSERT OR IGNORE INTO restaurant_cuisine (restaurant_id, cuisine)
        VALUES (?, ?);
    """, list(cuisine_rows))

    cursor.executemany("""
        INSERT OR IGNORE INTO locations (neighborhood) VALUES (?);
    """, list(distinct_locs))

    cursor.executemany("""
        INSERT OR IGNORE INTO cuisines (cuisine) VALUES (?);
    """, list(distinct_cuis))

    # Create indexes as required by architecture §6.3 & implementation-plan Task 7
    cursor.execute("CREATE INDEX idx_restaurants_neighborhood ON restaurants(neighborhood);")
    cursor.execute("CREATE INDEX idx_restaurants_listed_city ON restaurants(listed_city);")
    cursor.execute("CREATE INDEX idx_restaurants_rating ON restaurants(rating);")
    cursor.execute("CREATE INDEX idx_restaurants_cost ON restaurants(cost_for_two);")
    cursor.execute("CREATE INDEX idx_cuisine_lookup ON restaurant_cuisine(cuisine);")

    conn.commit()
    conn.close()
    logger.info("Saved %d restaurant records to SQLite at %s", len(records), path)


def save_to_parquet(records: list[dict[str, Any]], parquet_path: Path | str) -> None:
    """
    Persist cleaned records to Parquet file snapshot.
    """
    path = Path(parquet_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(records)
        pq.write_table(table, str(path))
    except Exception:
        import pandas as pd
        df = pd.DataFrame(records)
        df.to_parquet(str(path), index=False)
    logger.info("Saved %d restaurant records to Parquet at %s", len(records), path)


# ============================================================================
# Main Ingestion Workflow
# ============================================================================

def run_ingest(
    dataset_name: str | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Run end-to-end ingestion:
    1. Load Hugging Face dataset
    2. Clean and deduplicate
    3. Persist to SQLite and Parquet
    4. Print summary
    """
    root_dir = Path(__file__).resolve().parents[3]
    load_dotenv(root_dir / ".env")

    hf_dataset = dataset_name or os.getenv("HF_DATASET", "ManikaSaini/zomato-restaurant-recommendation")

    if output_dir:
        processed_dir = Path(output_dir)
    else:
        env_db_path = os.getenv("CATALOG_DB_PATH")
        if env_db_path:
            processed_dir = (root_dir / env_db_path).parent
        else:
            processed_dir = root_dir / "data" / "processed"

    sqlite_path = processed_dir / "restaurants.sqlite"
    parquet_path = processed_dir / "restaurants.parquet"

    logger.info("Loading dataset: %s", hf_dataset)
    import datasets
    ds = datasets.load_dataset(hf_dataset, split="train")

    logger.info("Cleaning and deduplicating %d raw records...", len(ds))
    records, stats = clean_and_deduplicate(ds)

    logger.info("Writing output files to %s...", processed_dir)
    save_to_sqlite(records, sqlite_path)
    save_to_parquet(records, parquet_path)

    # Print summary (Task 10)
    print("\n" + "=" * 50)
    print("      DINEMATE DATA INGESTION SUMMARY      ")
    print("=" * 50)
    print(f" Raw rows processed:         {stats['row_count_in']:,}")
    print(f" Rows dropped (empty name):  {stats['empty_name_dropped']:,}")
    print(f" Unique restaurants saved:   {stats['row_count_out']:,}")
    print(f" Distinct neighborhoods:     {stats['distinct_neighborhoods']:,}")
    print(f" Distinct cuisines:          {stats['distinct_cuisines']:,}")
    print(f" SQLite catalog path:        {sqlite_path}")
    print(f" Parquet catalog path:       {parquet_path}")
    print("=" * 50 + "\n")

    return stats


if __name__ == "__main__":
    run_ingest()

"""
Unit tests for Catalog Ingest (Phase 1).
Tests rating/cost parsers, cuisine splitting, dedup logic, empty name handling,
and end-to-end SQLite persistence from a 10-row raw fixture.
"""

import json
import sqlite3
import pytest
from app.catalog.ingest import (
    clean_and_deduplicate,
    generate_restaurant_id,
    parse_bool,
    parse_cost,
    parse_cuisines,
    parse_rate,
    parse_review_snippets,
    parse_votes,
    save_to_sqlite,
)


# ============================================================================
# 1. Parser Tests
# ============================================================================

def test_parse_rate():
    assert parse_rate("4.1/5") == 4.1
    assert parse_rate("4.1 / 5") == 4.1
    assert parse_rate("3.5") == 3.5
    assert parse_rate("NEW") is None
    assert parse_rate("-") is None
    assert parse_rate("") is None
    assert parse_rate(None) is None
    assert parse_rate("garbage") is None
    assert parse_rate("6.5/5") is None  # out of [0, 5] range


def test_parse_cost():
    assert parse_cost("800") == 800
    assert parse_cost("1,200") == 1200
    assert parse_cost("2,500.00") == 2500
    assert parse_cost(800) == 800
    assert parse_cost(1200.0) == 1200
    assert parse_cost("-") is None
    assert parse_cost("NEW") is None
    assert parse_cost("") is None
    assert parse_cost(None) is None
    assert parse_cost("0") is None
    assert parse_cost("junk") is None


def test_parse_cuisines():
    assert parse_cuisines("North Indian, Mughlai, Chinese") == [
        "North Indian",
        "Mughlai",
        "Chinese",
    ]
    # Trim, deduplicate case-insensitively, preserve order
    assert parse_cuisines(" Cafe , Italian , cafe , Desserts ") == [
        "Cafe",
        "Italian",
        "Desserts",
    ]
    assert parse_cuisines("") == []
    assert parse_cuisines(None) == []


def test_parse_votes():
    assert parse_votes(775) == 775
    assert parse_votes("775") == 775
    assert parse_votes("1,250") == 1250
    assert parse_votes(None) == 0
    assert parse_votes("abc") == 0


def test_parse_bool():
    assert parse_bool("Yes") is True
    assert parse_bool("yes") is True
    assert parse_bool("Y") is True
    assert parse_bool(True) is True
    assert parse_bool("No") is False
    assert parse_bool("") is False
    assert parse_bool(None) is False


def test_parse_review_snippets():
    raw_reviews = (
        "[('Rated 4.0', 'RATED\\n  A beautiful place to dine in. The interiors take you back to the Mughal era.'), "
        "('Rated 5.0', 'RATED\\n  Great food and pleasant ambience. Highly recommended.')]"
    )
    snippets = parse_review_snippets(raw_reviews, max_snippets=2)
    assert len(snippets) == 2
    assert "A beautiful place to dine in" in snippets[0]
    assert "RATED" not in snippets[0]
    assert "Great food and pleasant ambience" in snippets[1]
    assert parse_review_snippets("[]") == []
    assert parse_review_snippets(None) == []


def test_generate_restaurant_id():
    id1 = generate_restaurant_id("Jalsa", "Banashankari, Bangalore")
    id2 = generate_restaurant_id("jalsa", "banashankari, bangalore ")
    assert id1 == id2
    assert len(id1) == 16


# ============================================================================
# 2. Deduplication & Cleaning Tests
# ============================================================================

def test_empty_name_rows_dropped():
    raw_data = [
        {"name": "", "address": "Addr 1", "rate": "4.0/5"},
        {"name": None, "address": "Addr 2", "rate": "3.5/5"},
        {"name": "   ", "address": "Addr 3", "rate": "4.5/5"},
        {"name": "Valid Cafe", "address": "Addr 4", "rate": "4.2/5", "location": "Koramangala"},
    ]
    cleaned, stats = clean_and_deduplicate(raw_data)
    assert len(cleaned) == 1
    assert cleaned[0]["name"] == "Valid Cafe"
    assert stats["empty_name_dropped"] == 3
    assert stats["row_count_out"] == 1


def test_dedup_collapses_duplicate_listings():
    # Same name + address appears with different listed_in(type) and rest_type
    raw_data = [
        {
            "name": "Truffles",
            "address": "St. Marks Road, Bangalore",
            "location": "St. Marks Road",
            "listed_in(city)": "Brigade Road",
            "listed_in(type)": "Dine-out",
            "rest_type": "Cafe",
            "cuisines": "Cafe, Burger, American",
            "rate": "4.5/5",
            "votes": "1200",
            "approx_cost(for two people)": "900",
        },
        {
            "name": "Truffles",
            "address": "St. Marks Road, Bangalore",
            "location": "St. Marks Road",
            "listed_in(city)": "Church Street",
            "listed_in(type)": "Delivery",
            "rest_type": "Quick Bites",
            "cuisines": "Cafe, Desserts",
            "rate": "4.6/5",
            "votes": "1500",
            "approx_cost(for two people)": "900",
        },
    ]
    cleaned, stats = clean_and_deduplicate(raw_data)
    assert len(cleaned) == 1
    item = cleaned[0]
    assert item["name"] == "Truffles"
    # rest_types and listed_types merged
    assert "Cafe" in item["rest_types"]
    assert "Quick Bites" in item["rest_types"]
    assert "Dine-out" in item["listed_types"]
    assert "Delivery" in item["listed_types"]
    # votes took the highest (1500)
    assert item["votes"] == 1500
    # cuisines unioned
    assert "Burger" in item["cuisines"]
    assert "Desserts" in item["cuisines"]
    assert stats["row_count_in"] == 2
    assert stats["row_count_out"] == 1


# ============================================================================
# 3. Raw-like 10-Row Fixture to SQLite Test
# ============================================================================

SAMPLE_RAW_FIXTURE = [
    {
        "url": "https://www.zomato.com/bangalore/jalsa-banashankari",
        "address": "942, 21st Main Road, 2nd Stage, Banashankari, Bangalore",
        "name": "Jalsa",
        "online_order": "Yes",
        "book_table": "Yes",
        "rate": "4.1/5",
        "votes": "775",
        "phone": "080 42297555",
        "location": "Banashankari",
        "rest_type": "Casual Dining",
        "dish_liked": "Pasta, Lunch Buffet, Masala Papad",
        "cuisines": "North Indian, Mughlai, Chinese",
        "approx_cost(for two people)": "800",
        "reviews_list": "[('Rated 4.0', 'RATED\\n  A beautiful place to dine in.')]",
        "menu_item": "[]",
        "listed_in(type)": "Buffet",
        "listed_in(city)": "Banashankari",
    },
    {
        "url": "https://www.zomato.com/bangalore/jalsa-banashankari-dineout",
        "address": "942, 21st Main Road, 2nd Stage, Banashankari, Bangalore",
        "name": "Jalsa",
        "online_order": "Yes",
        "book_table": "Yes",
        "rate": "4.1/5",
        "votes": "780",
        "phone": "080 42297555",
        "location": "Banashankari",
        "rest_type": "Casual Dining",
        "dish_liked": "Pasta, Dum Biryani",
        "cuisines": "North Indian, Mughlai",
        "approx_cost(for two people)": "800",
        "reviews_list": "[('Rated 4.0', 'RATED\\n  Lovely food and vibe.')]",
        "menu_item": "[]",
        "listed_in(type)": "Dine-out",
        "listed_in(city)": "Banashankari",
    },
    {
        "name": "Spice Elephant",
        "address": "2nd Floor, Banashankari, Bangalore",
        "location": "Banashankari",
        "listed_in(city)": "Banashankari",
        "listed_in(type)": "Buffet",
        "rest_type": "Casual Dining",
        "cuisines": "Chinese, North Indian, Thai",
        "rate": "4.1/5",
        "votes": "787",
        "approx_cost(for two people)": "800",
        "online_order": "Yes",
        "book_table": "No",
    },
    {
        "name": "San Churro Cafe",
        "address": "1st Stage, Banashankari, Bangalore",
        "location": "Banashankari",
        "listed_in(city)": "Banashankari",
        "listed_in(type)": "Cafes",
        "rest_type": "Cafe, Casual Dining",
        "cuisines": "Cafe, Mexican, Italian",
        "rate": "3.8/5",
        "votes": "918",
        "approx_cost(for two people)": "800",
        "online_order": "Yes",
        "book_table": "No",
    },
    {
        "name": "Addhuri Udupi Bhojana",
        "address": "1st Floor, Banashankari, Bangalore",
        "location": "Banashankari",
        "listed_in(city)": "Banashankari",
        "listed_in(type)": "Delivery",
        "rest_type": "Quick Bites",
        "cuisines": "South Indian",
        "rate": "3.7/5",
        "votes": "88",
        "approx_cost(for two people)": "300",
        "online_order": "No",
        "book_table": "No",
    },
    {
        "name": "Empire Restaurant",
        "address": "Koramangala 5th Block, Bangalore",
        "location": "Koramangala 5th Block",
        "listed_in(city)": "Koramangala",
        "listed_in(type)": "Dine-out",
        "rest_type": "Casual Dining",
        "cuisines": "North Indian, Mughlai, South Indian",
        "rate": "4.2/5",
        "votes": "4500",
        "approx_cost(for two people)": "750",
        "online_order": "Yes",
        "book_table": "Yes",
    },
    {
        "name": "Meghana Foods",
        "address": "Residency Road, Bangalore",
        "location": "Residency Road",
        "listed_in(city)": "Brigade Road",
        "listed_in(type)": "Delivery",
        "rest_type": "Casual Dining",
        "cuisines": "Biryani, Andhra, North Indian",
        "rate": "4.4/5",
        "votes": "3800",
        "approx_cost(for two people)": "600",
        "online_order": "Yes",
        "book_table": "No",
    },
    {
        "name": "Corner House Ice Cream",
        "address": "Indiranagar 100ft Road, Bangalore",
        "location": "Indiranagar",
        "listed_in(city)": "Indiranagar",
        "listed_in(type)": "Desserts",
        "rest_type": "Dessert Parlor",
        "cuisines": "Ice Cream, Desserts",
        "rate": "4.6/5",
        "votes": "2100",
        "approx_cost(for two people)": "400",
        "online_order": "Yes",
        "book_table": "No",
    },
    {
        "name": "New Eatery",
        "address": "HSR Layout, Bangalore",
        "location": "HSR Layout",
        "listed_in(city)": "HSR",
        "listed_in(type)": "Delivery",
        "rest_type": "Quick Bites",
        "cuisines": "Fast Food",
        "rate": "NEW",
        "votes": "0",
        "approx_cost(for two people)": "-",
        "online_order": "No",
        "book_table": "No",
    },
    {
        # Row with missing name - should be dropped
        "name": "",
        "address": "Invalid row",
        "rate": "3.5/5",
    },
]


def test_fixture_produces_expected_sqlite(tmp_path):
    sqlite_file = tmp_path / "test_catalog.sqlite"
    cleaned, stats = clean_and_deduplicate(SAMPLE_RAW_FIXTURE)

    # 10 raw rows, 1 empty name dropped, 2 Jalsa rows deduplicated into 1 -> 8 output restaurants
    assert stats["row_count_in"] == 10
    assert stats["empty_name_dropped"] == 1
    assert stats["row_count_out"] == 8

    save_to_sqlite(cleaned, sqlite_file)
    assert sqlite_file.exists()

    conn = sqlite3.connect(str(sqlite_file))
    cursor = conn.cursor()

    # Query restaurants count
    cursor.execute("SELECT COUNT(*) FROM restaurants;")
    assert cursor.fetchone()[0] == 8

    # Query Jalsa deduped row
    cursor.execute("SELECT name, rating, cost_for_two, votes, rest_types, listed_types FROM restaurants WHERE name = 'Jalsa';")
    jalsa = cursor.fetchone()
    assert jalsa is not None
    assert jalsa[0] == "Jalsa"
    assert jalsa[1] == 4.1
    assert jalsa[2] == 800
    assert jalsa[3] == 780  # highest vote retained
    rest_types = json.loads(jalsa[4])
    listed_types = json.loads(jalsa[5])
    assert "Casual Dining" in rest_types
    assert "Buffet" in listed_types
    assert "Dine-out" in listed_types

    # Ensure phone and menu_item columns do NOT exist in restaurants table
    cursor.execute("PRAGMA table_info(restaurants);")
    col_names = [row[1] for row in cursor.fetchall()]
    assert "phone" not in col_names
    assert "menu_item" not in col_names

    # Check cuisine junction table
    cursor.execute("SELECT cuisine FROM restaurant_cuisine WHERE restaurant_id = (SELECT id FROM restaurants WHERE name = 'Jalsa') ORDER BY cuisine;")
    jalsa_cuisines = [r[0] for r in cursor.fetchall()]
    assert "Chinese" in jalsa_cuisines
    assert "North Indian" in jalsa_cuisines

    # Check locations table
    cursor.execute("SELECT neighborhood FROM locations ORDER BY neighborhood;")
    locs = [r[0] for r in cursor.fetchall()]
    assert "Banashankari" in locs
    assert "Indiranagar" in locs

    conn.close()

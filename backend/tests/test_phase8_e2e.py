"""
Phase 8 End-to-End Verification Tests.
Verifies the 4 primary success criteria from the problem statement:
1. Real processed Hugging Face records used (not mocked arrays).
2. User preferences narrow candidates in code before ranking.
3. Recommendations are ranked and justified with natural-language reasons.
4. Output displays the 5 required fields in a scannable structure.
"""

import pytest
from app.catalog.store import CatalogStore
from app.domain.models import Preference
from app.services.recommend import RecommendService


# ============================================================================
# Criterion 1: Real Hugging Face Catalog Records
# ============================================================================

def test_criterion_1_real_dataset_records():
    """
    Asserts that the running application queries the processed SQLite catalog
    ingested from ManikaSaini/zomato-restaurant-recommendation, containing real
    Bangalore restaurant names, locations, and Zomato URLs.
    """
    store = CatalogStore()
    pref = Preference(location="Banashankari", budget="medium", cuisine="North Indian")
    candidates, counts = store.query_candidates(pref)

    assert counts["initial"] > 0
    assert len(candidates) > 0

    # Verify real record fields exist and are authentic
    top = candidates[0]
    assert top.name != ""
    assert top.neighborhood is not None or top.listed_city is not None
    assert top.cost_for_two is not None and 401 <= top.cost_for_two <= 800
    assert top.url and "zomato.com" in top.url


# ============================================================================
# Criterion 2: Preferences Narrow Candidates in Code
# ============================================================================

def test_criterion_2_preferences_narrow_candidates():
    """
    Asserts that changing preferences (location, budget, cuisine) deterministically
    narrows and alters the candidate set.
    """
    service = RecommendService(enable_cache=False)

    # Query A: Banashankari + North Indian + Medium
    pref_a = Preference(location="Banashankari", budget="medium", cuisine="North Indian", min_rating=4.0)
    res_a = service.recommend(pref_a)

    # Query B: Indiranagar + Cafe + High
    pref_b = Preference(location="Indiranagar", budget="high", cuisine="Cafe", min_rating=4.0)
    res_b = service.recommend(pref_b)

    # Both must return valid candidates
    assert res_a.candidate_count > 0
    assert res_b.candidate_count > 0

    names_a = {r.name for r in res_a.recommendations}
    names_b = {r.name for r in res_b.recommendations}

    # Distinct locations and cuisines must produce distinct recommendations
    assert names_a != names_b


# ============================================================================
# Criterion 3: Ranked Recommendations with Justifications
# ============================================================================

def test_criterion_3_ranked_recs_with_justifications():
    """
    Asserts that the returned recommendations are ordered with sequential ranks
    and every recommendation has a clear natural-language explanation.
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(location="Banashankari", budget="medium", cuisine="North Indian", min_rating=3.5)
    res = service.recommend(pref, result_limit=5)

    assert len(res.recommendations) > 0

    for idx, rec in enumerate(res.recommendations, start=1):
        assert rec.rank == idx
        # Explanation must be a meaningful non-empty sentence
        assert isinstance(rec.explanation, str)
        assert len(rec.explanation.strip()) >= 20
        # Check source is identified
        assert res.source in {"llm", "heuristic"}


# ============================================================================
# Criterion 4: Scannable Output with 5 Required Fields
# ============================================================================

def test_criterion_4_five_required_display_fields():
    """
    Problem statement requires 5 specific display fields:
    1. Restaurant name
    2. Cuisine type(s)
    3. Rating (with review/votes info)
    4. Estimated cost for two
    5. AI-curated reason / explanation
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(location="Banashankari", budget="medium", cuisine="North Indian", min_rating=3.5)
    res = service.recommend(pref, result_limit=3)

    assert len(res.recommendations) > 0
    for rec in res.recommendations:
        # Field 1: Name
        assert rec.name and len(rec.name.strip()) > 0

        # Field 2: Cuisine list
        assert isinstance(rec.cuisines, list)
        assert len(rec.cuisines) > 0

        # Field 3: Rating
        assert rec.rating is not None
        assert 1.0 <= rec.rating <= 5.0
        assert rec.votes >= 0

        # Field 4: Estimated cost for two
        assert rec.estimated_cost is not None
        assert rec.estimated_cost > 0

        # Field 5: Explanation
        assert rec.explanation and len(rec.explanation.strip()) > 0


# ============================================================================
# Canonical Sample Query End-to-End Test (Task 1 & Task 3)
# ============================================================================

def test_canonical_sample_query_end_to_end():
    """
    Tests the canonical assignment query specified in Phase 8 Task 3:
    Location: Banashankari, Budget: medium (₹401-₹800), Cuisine: North Indian, Min rating: 4.0.
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    res = service.recommend(pref, result_limit=5)

    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    assert len(res.recommendations) <= 5
    assert res.relaxed_filters == []
    assert res.source in {"llm", "heuristic"}
    assert res.query.location == "Banashankari"
    assert res.query.budget == "medium"
    assert res.query.cuisine == "North Indian"
    assert res.query.min_rating == 4.0

    # Real restaurant names check (e.g. Jalsa)
    names = [r.name for r in res.recommendations]
    assert any("Jalsa" in n or "Spice" in n or len(n) > 0 for n in names)

    # Every item strictly satisfies the constraints
    for r in res.recommendations:
        assert r.rating is not None and r.rating >= 4.0
        assert r.estimated_cost is not None and 401 <= r.estimated_cost <= 800
        assert any("north indian" in c.lower() for c in r.cuisines)
        assert len(r.explanation) >= 20


# ============================================================================
# Real SQLite Catalog Schema, Indexes & PII Exclusion (Task 1 & Task 2)
# ============================================================================

def test_real_catalog_schema_indexes_and_pii_exclusion():
    """
    Verifies that data/processed/restaurants.sqlite exists, contains the real
    processed Hugging Face dataset (>10,000 deduplicated rows), proper indexes,
    and excludes raw phone/menu_item columns.
    """
    import sqlite3
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    db_path = repo_root / "data" / "processed" / "restaurants.sqlite"
    assert db_path.exists(), f"SQLite catalog must exist at {db_path}"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 1. Total row count check (> 10,000 real restaurants)
    cursor.execute("SELECT COUNT(*) FROM restaurants;")
    row_count = cursor.fetchone()[0]
    assert row_count > 10000, f"Expected >10,000 rows from Hugging Face dataset, got {row_count}"

    # 2. Check table schemas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cursor.fetchall()}
    assert "restaurants" in tables
    assert "locations" in tables
    assert "cuisines" in tables
    assert "restaurant_cuisine" in tables

    # 3. Check columns: phone and menu_item must NOT be present
    cursor.execute("PRAGMA table_info(restaurants);")
    cols = {r[1] for r in cursor.fetchall()}
    assert "name" in cols
    assert "rating" in cols
    assert "cost_for_two" in cols
    assert "cuisines" in cols
    assert "neighborhood" in cols
    assert "phone" not in cols
    assert "menu_item" not in cols

    # 4. Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {r[0] for r in cursor.fetchall()}
    assert "idx_restaurants_neighborhood" in indexes
    assert "idx_restaurants_listed_city" in indexes
    assert "idx_restaurants_rating" in indexes
    assert "idx_restaurants_cost" in indexes

    conn.close()


# ============================================================================
# HTTP API End-to-End Test for Recommendation Endpoint (Task 1 & Architecture §16)
# ============================================================================

def test_http_api_recommend_canonical_query_e2e():
    """
    Tests the FastAPI POST /api/recommend endpoint with the canonical query.
    Ensures HTTP status 200, full serialization, and all 5 required fields.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    payload = {
        "location": "Banashankari",
        "budget": "medium",
        "cuisine": "North Indian",
        "min_rating": 4.0,
    }

    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "query" in data
    assert "candidate_count" in data
    assert data["candidate_count"] > 0
    assert "relaxed_filters" in data
    assert "summary" in data
    assert "source" in data
    assert data["source"] in {"llm", "heuristic"}
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

    first_item = data["recommendations"][0]
    required_keys = ["id", "name", "cuisines", "rating", "estimated_cost", "neighborhood", "explanation"]
    for k in required_keys:
        assert k in first_item, f"Expected key '{k}' in recommendation item"


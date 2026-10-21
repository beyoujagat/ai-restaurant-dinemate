"""
Unit and integration tests for Phase 2:
CatalogStore, Preference validation, Budget helpers, and Candidate Filters.
"""

import math
import pytest
from pydantic import ValidationError

from app.catalog.filters import (
    apply_candidate_filters,
    filter_by_budget,
    filter_by_cuisine,
    filter_by_extras,
    filter_by_location,
    filter_by_min_rating,
    score_candidate,
)
from app.catalog.store import CatalogNotFoundError, CatalogStore
from app.domain.budget import (
    get_budget_band,
    get_budget_bounds,
    get_budget_label,
    is_in_budget,
)
from app.domain.models import Preference, Restaurant
from tests.fixtures.sample_catalog import FIXTURE_RESTAURANTS


# ============================================================================
# 1. Budget Helper & Boundary Tests
# ============================================================================

def test_budget_boundaries():
    # Low <= 400
    assert get_budget_band(150) == "low"
    assert get_budget_band(300) == "low"
    assert get_budget_band(400) == "low"  # Exact low boundary

    # Medium 401 - 800
    assert get_budget_band(401) == "medium"  # Exact medium lower boundary
    assert get_budget_band(600) == "medium"
    assert get_budget_band(800) == "medium"  # Exact medium upper boundary

    # High >= 801
    assert get_budget_band(801) == "high"  # Exact high lower boundary
    assert get_budget_band(1200) == "high"
    assert get_budget_band(2500) == "high"

    # Missing cost
    assert get_budget_band(None) is None


def test_is_in_budget():
    assert is_in_budget(400, "low") is True
    assert is_in_budget(401, "low") is False

    assert is_in_budget(400, "medium") is False
    assert is_in_budget(401, "medium") is True
    assert is_in_budget(800, "medium") is True
    assert is_in_budget(801, "medium") is False

    assert is_in_budget(800, "high") is False
    assert is_in_budget(801, "high") is True

    # Missing cost fails any specified budget band
    assert is_in_budget(None, "medium") is False
    # If no budget band requested, pass
    assert is_in_budget(None, None) is True
    assert is_in_budget(500, None) is True


def test_budget_bounds_and_labels():
    assert get_budget_bounds("low") == (None, 400)
    assert get_budget_bounds("medium") == (401, 800)
    assert get_budget_bounds("high") == (801, None)

    assert "400" in get_budget_label("low")
    assert "401" in get_budget_label("medium")
    assert "801" in get_budget_label("high")


# ============================================================================
# 2. Preference Validation Tests
# ============================================================================

def test_preference_validation_valid():
    pref = Preference(
        location="  Banashankari  ",
        budget="MEDIUM",
        cuisine=" Italian ",
        min_rating=4.0,
        extras="family-friendly",
    )
    assert pref.location == "Banashankari"
    assert pref.budget == "medium"
    assert pref.cuisine == "Italian"
    assert pref.min_rating == 4.0


def test_preference_validation_invalid_budget():
    with pytest.raises(ValidationError):
        Preference(budget="super_cheap")


def test_preference_validation_invalid_rating():
    with pytest.raises(ValidationError):
        Preference(min_rating=-0.5)

    with pytest.raises(ValidationError):
        Preference(min_rating=5.5)


# ============================================================================
# 3. Filters in Isolation
# ============================================================================

def test_filter_by_location_neighborhood_and_listed_city():
    # Match neighborhood
    bsk = filter_by_location(FIXTURE_RESTAURANTS, "Banashankari")
    assert len(bsk) == 10
    assert all("Banashankari" in (r.neighborhood + r.listed_city) for r in bsk)

    # Match listed_city (e.g. Brigade Road lists Church Street restaurants)
    brigade = filter_by_location(FIXTURE_RESTAURANTS, "Brigade Road")
    assert len(brigade) >= 3
    assert any(r.neighborhood == "Church Street" for r in brigade)

    # Case-insensitivity
    bsk_lower = filter_by_location(FIXTURE_RESTAURANTS, "banashankari")
    assert len(bsk_lower) == 10


def test_filter_by_budget_isolation():
    low = filter_by_budget(FIXTURE_RESTAURANTS, "low")
    assert len(low) > 0
    assert all(r.cost_for_two is not None and r.cost_for_two <= 400 for r in low)

    med = filter_by_budget(FIXTURE_RESTAURANTS, "medium")
    assert len(med) > 0
    assert all(r.cost_for_two is not None and 401 <= r.cost_for_two <= 800 for r in med)

    high = filter_by_budget(FIXTURE_RESTAURANTS, "high")
    assert len(high) > 0
    assert all(r.cost_for_two is not None and r.cost_for_two >= 801 for r in high)

    # Restaurant with None cost (bs-9) must NOT be in any budget band
    none_cost_ids = {r.id for r in FIXTURE_RESTAURANTS if r.cost_for_two is None}
    assert none_cost_ids.isdisjoint({r.id for r in low})
    assert none_cost_ids.isdisjoint({r.id for r in med})
    assert none_cost_ids.isdisjoint({r.id for r in high})


def test_filter_by_cuisine_isolation():
    italian = filter_by_cuisine(FIXTURE_RESTAURANTS, "Italian")
    assert len(italian) > 0
    for r in italian:
        assert any("italian" in c.lower() for c in r.cuisines) or "italian" in r.cuisines_raw.lower()

    # Case insensitive
    italian_lower = filter_by_cuisine(FIXTURE_RESTAURANTS, "italian")
    assert len(italian) == len(italian_lower)


def test_filter_by_min_rating_isolation():
    min_4 = filter_by_min_rating(FIXTURE_RESTAURANTS, 4.0)
    assert len(min_4) > 0
    assert all(r.rating is not None and r.rating >= 4.0 for r in min_4)

    # Explicit check: bs-8 has rating=None; it MUST be excluded
    assert "bs-8" not in [r.id for r in min_4]
    # bs-7 has rating 3.2; it MUST be excluded
    assert "bs-7" not in [r.id for r in min_4]


def test_filter_by_extras():
    table_booking = filter_by_extras(FIXTURE_RESTAURANTS, "table booking")
    assert all(r.book_table for r in table_booking)

    quick_bites = filter_by_extras(FIXTURE_RESTAURANTS, "quick bites")
    assert all(any("quick bites" in t.lower() for t in r.rest_types) for r in quick_bites)


# ============================================================================
# 4. Combined Filter & Exit Criteria Tests
# ============================================================================

def test_combined_filters_exit_criterion():
    """
    Exit criterion from Phase 2:
    Given { location: Banashankari, budget: medium, cuisine: Italian, min_rating: 4.0 },
    returns <= 12 candidates that ALL satisfy the hard constraints.
    """
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="Italian",
        min_rating=4.0,
    )

    candidates, counts = apply_candidate_filters(FIXTURE_RESTAURANTS, pref)

    # Must return <= 12 candidates
    assert len(candidates) <= 12
    assert len(candidates) > 0

    # Check that each returned candidate satisfies ALL hard constraints:
    for r in candidates:
        assert "Banashankari" in (r.neighborhood + r.listed_city)
        assert r.cost_for_two is not None and 401 <= r.cost_for_two <= 800
        assert any("italian" in c.lower() for c in r.cuisines)
        assert r.rating is not None and r.rating >= 4.0

    # Specifically in our fixture:
    # bs-2: Onesta Banashankari (cost 600, rating 4.6, Italian) -> MATCH
    # bs-10: Trattoria Bella (cost 401, rating 4.2, Italian) -> MATCH
    matched_names = [r.name for r in candidates]
    assert "Onesta Banashankari" in matched_names
    assert "Trattoria Bella" in matched_names

    # Verify exclusions:
    # bs-1 (Jalsa): North Indian -> excluded by cuisine
    assert "Jalsa" not in matched_names
    # bs-3 (Little Italy): cost 801 (high) -> excluded by budget
    assert "Little Italy Banashankari" not in matched_names
    # bs-4 (Italian Express): cost 400 (low) -> excluded by budget
    assert "Banashankari Italian Express" not in matched_names
    # bs-7 (Street Pasta): rating 3.2 -> excluded by rating
    assert "Street Pasta Point" not in matched_names
    # bs-8 (Mamma Mia): rating None -> excluded by rating
    assert "Mamma Mia Pizza" not in matched_names


def test_empty_result_set():
    pref = Preference(
        location="Banashankari",
        cuisine="NonExistentAlienCuisine",
    )
    candidates, counts = apply_candidate_filters(FIXTURE_RESTAURANTS, pref)
    assert candidates == []
    assert counts["sent_to_llm"] == 0


def test_candidate_cap_limit():
    """Verify that if dozens match, shortlist is capped at CANDIDATE_LIMIT (default 12)."""
    # Create 30 identical matching restaurants
    many_matches = [
        Restaurant(
            id=f"test-{i}",
            name=f"Cafe {i}",
            neighborhood="Indiranagar",
            cost_for_two=500,
            cuisines=["Cafe"],
            rating=4.0 + (i % 5) * 0.1,
            votes=100 * i,
        )
        for i in range(30)
    ]

    pref = Preference(location="Indiranagar", budget="medium", cuisine="Cafe")
    shortlist, counts = apply_candidate_filters(many_matches, pref, candidate_limit=12)

    assert len(shortlist) == 12
    # Verify pre-ranking order: score must be non-increasing
    scores = [score_candidate(r) for r in shortlist]
    assert scores == sorted(scores, reverse=True)


def test_pre_ranking_scoring():
    r1 = Restaurant(id="1", name="A", cost_for_two=500, rating=4.5, votes=1000)
    r2 = Restaurant(id="2", name="B", cost_for_two=500, rating=4.0, votes=100)
    r_unrated = Restaurant(id="3", name="C", cost_for_two=500, rating=None, votes=500)

    score1 = score_candidate(r1)
    score2 = score_candidate(r2)
    score_unrated = score_candidate(r_unrated)

    assert score1 > score2
    assert score_unrated == 0.0

    # Keyword boost check
    r_pasta = Restaurant(
        id="4",
        name="Pasta Palace",
        cost_for_two=500,
        rating=4.0,
        votes=500,
        dishes_liked=["Truffle Pasta", "Garlic Bread"],
    )
    score_no_boost = score_candidate(r_pasta)
    score_with_boost = score_candidate(r_pasta, extras="craving rich pasta dishes")
    assert score_with_boost > score_no_boost


# ============================================================================
# 5. CatalogStore Real Database Integration Tests
# ============================================================================

def test_catalog_store_real_db():
    store = CatalogStore()

    # Test facets are loaded from real DB (not hardcoded)
    locations = store.list_locations()
    assert len(locations) >= 50
    assert "Banashankari" in locations
    assert "Indiranagar" in locations

    cuisines = store.list_cuisines()
    assert len(cuisines) >= 50
    assert "North Indian" in cuisines
    assert "Italian" in cuisines

    # Test meta options
    opts = store.get_meta_options()
    assert "locations" in opts
    assert "cuisines" in opts
    assert "budget_labels" in opts
    assert opts["budget_labels"]["medium"] == "₹401–₹800 for two"

    # Test end-to-end query on real catalog: Banashankari, medium, North Indian, min 4.0
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    candidates, counts = store.query_candidates(pref)

    assert len(candidates) <= 12
    assert len(candidates) > 0
    # Jalsa should be among the top candidates!
    names = [r.name for r in candidates]
    assert "Jalsa" in names

    # Verify all returned candidates satisfy the hard constraints
    for r in candidates:
        assert "Banashankari" in (r.neighborhood + r.listed_city)
        assert r.cost_for_two is not None and 401 <= r.cost_for_two <= 800
        assert any("north indian" in c.lower() for c in r.cuisines)
        assert r.rating is not None and r.rating >= 4.0


def test_catalog_store_missing_db(tmp_path):
    fake_path = tmp_path / "non_existent.sqlite"
    with pytest.raises(CatalogNotFoundError):
        CatalogStore(fake_path)

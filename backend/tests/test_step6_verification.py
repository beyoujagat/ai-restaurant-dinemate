"""
Step 6 End-to-End Verification Tests.
Verifies the complete geo-proximity and UI empty-state implementation:
1. API nearby endpoint (/api/meta/nearby)
2. Strict query execution (relaxed_filters == [])
3. 5 km and 10 km geo-expansions on real catalog data
4. Broad area gating (Central Bangalore skips radius expansion)
5. High-budget guardrail preservation
6. Frontend copy and empty state action contracts
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.routes import router
from app.catalog.store import CatalogStore
from app.domain.models import Preference
from app.main import app
from app.services.recommend import RecommendService


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


# ============================================================================
# 1. API Nearby Endpoint Checks
# ============================================================================

def test_api_nearby_endpoint_structure_and_sorting(api_client):
    """
    Asserts that GET /api/meta/nearby returns verified 5 km and 10 km bands,
    with distances accurately computed, rounded, and sorted ascending.
    """
    resp = api_client.get("/api/meta/nearby?location=Indiranagar")
    assert resp.status_code == 200
    data = resp.json()

    assert data["location"] == "Indiranagar"
    assert "nearby_5km" in data
    assert "nearby_10km" in data

    nearby_5km = data["nearby_5km"]
    nearby_10km = data["nearby_10km"]

    assert len(nearby_5km) > 0
    assert len(nearby_10km) >= len(nearby_5km)

    # Check ascending distance order
    distances_5km = [item["distance_km"] for item in nearby_5km]
    assert distances_5km == sorted(distances_5km)

    # Check key known neighbours
    names_5km = [item["name"] for item in nearby_5km]
    assert "Domlur" in names_5km
    assert "Ulsoor" in names_5km

    # Verify distances are within expected 5 km bounds
    for item in nearby_5km:
        assert 0.0 < item["distance_km"] <= 5.0

    for item in nearby_10km:
        assert 0.0 < item["distance_km"] <= 10.0


def test_api_nearby_endpoint_broad_area(api_client):
    """
    Asserts that broad regional areas (Central Bangalore) return empty nearby lists.
    """
    resp = api_client.get("/api/meta/nearby?location=Central%20Bangalore")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nearby_5km"] == []
    assert data["nearby_10km"] == []


def test_api_nearby_endpoint_unknown_location(api_client):
    """
    Asserts that unknown or unverified locations return empty lists gracefully.
    """
    resp = api_client.get("/api/meta/nearby?location=UnknownFictionalLocality")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nearby_5km"] == []
    assert data["nearby_10km"] == []


# ============================================================================
# 2. Recommendation Engine: Expansion Tiers & Strict Matching
# ============================================================================

def test_strict_query_returns_empty_relaxed_filters():
    """
    Popular query in Koramangala 5th Block matches strictly without filter relaxation.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    pref = Preference(location="Koramangala 5th Block", budget="medium", cuisine="Cafe")
    res = service.recommend(pref)

    assert res.candidate_count > 0
    assert res.relaxed_filters == []
    assert len(res.recommendations) > 0
    assert all(r.neighborhood == "Koramangala 5th Block" for r in res.recommendations)


def test_5km_expansion_on_real_catalog():
    """
    Indiranagar + Low Budget + Assamese:
    1. Strict initial search returns 0 candidates (does NOT silently expand to other neighbourhoods).
    2. Explicit nearby search (include_nearby=True) discovers Taste of Assam (Koramangala 4th Block).
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    # Initial strict search: must return 0 candidates
    pref_strict = Preference(location="Indiranagar", budget="low", cuisine="Assamese", include_nearby=False)
    res_strict = service.recommend(pref_strict)
    assert res_strict.candidate_count == 0
    assert res_strict.recommendations == []
    assert res_strict.relaxed_filters == []

    # Explicit nearby search requested by user: expands to 5 km
    pref_nearby = Preference(location="Indiranagar", budget="low", cuisine="Assamese", include_nearby=True)
    res_nearby = service.recommend(pref_nearby)
    assert res_nearby.candidate_count > 0
    assert "location_expanded_5km" in res_nearby.relaxed_filters
    assert "location_expanded_10km" not in res_nearby.relaxed_filters
    assert len(res_nearby.recommendations) > 0
    assert res_nearby.recommendations[0].distance_km is not None


def test_10km_expansion_on_real_catalog():
    """
    Indiranagar + Low Budget + Australian:
    1. Strict initial search returns 0 candidates (no silent expansion).
    2. Explicit nearby search (include_nearby=True) discovers candidates within 10 km.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    pref_strict = Preference(location="Indiranagar", budget="low", cuisine="Australian", include_nearby=False)
    res_strict = service.recommend(pref_strict)
    assert res_strict.candidate_count == 0
    assert res_strict.recommendations == []

    pref_nearby = Preference(location="Indiranagar", budget="low", cuisine="Australian", include_nearby=True)
    res_nearby = service.recommend(pref_nearby)
    assert res_nearby.candidate_count > 0
    assert "location_expanded_10km" in res_nearby.relaxed_filters
    assert len(res_nearby.recommendations) > 0


def test_broad_area_skips_radius_expansion():
    """
    Central Bangalore is a broad regional area. Radius expansion must be inhibited
    even when include_nearby is True.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    pref = Preference(location="Central Bangalore", budget="low", cuisine="Assamese", include_nearby=True)
    res = service.recommend(pref)

    # Should not expand radius for broad area
    assert res.candidate_count == 0
    assert res.recommendations == []
    assert "location_expanded_5km" not in res.relaxed_filters
    assert "location_expanded_10km" not in res.relaxed_filters


def test_high_budget_guardrail_never_relaxed():
    """
    High budget intent must never be relaxed down to medium/low.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    pref = Preference(location="Central Bangalore", budget="high", cuisine="Assamese")
    res = service.recommend(pref)

    assert res.candidate_count == 0
    assert "budget" not in res.relaxed_filters


# ============================================================================
# 3. UI Contracts & Empty-State Component Verification
# ============================================================================

def test_frontend_empty_state_contracts():
    """
    Verify frontend code artifacts for required user behaviours:
    - formatRelaxationNotice handles 5km, 10km, budget, extras
    - EmptyState displays dynamic budget actions ("Widen Budget to Medium/High", "Widen Budget to High", "Explore All Budgets")
    - Dedicated nearby search button is present when eligible alternatives exist
    - Nearby search button is hidden when no eligible alternatives exist
    - Hardcoded hubs are completely removed from EmptyState
    - Real verified nearby neighbourhoods are retrieved via fetchNearbyNeighbourhoods
    """
    repo_root = Path(__file__).resolve().parents[2]
    empty_path = repo_root / "frontend" / "src" / "components" / "EmptyState.tsx"
    rec_path = repo_root / "frontend" / "src" / "pages" / "RecommendPage.tsx"

    assert empty_path.exists()
    assert rec_path.exists()

    empty_code = empty_path.read_text(encoding="utf-8")
    rec_code = rec_path.read_text(encoding="utf-8")

    # 1. No hardcoded foodie hubs
    assert "Try nearby foodie hubs like" not in empty_code
    assert "Koramangala, Indiranagar, or Jayanagar" not in empty_code

    # 2. Verified nearby data integration
    assert "fetchNearbyNeighbourhoods" in empty_code
    assert "nearby_5km" in empty_code
    assert "nearby_10km" in empty_code
    assert "btn-nearby-chip" in empty_code
    assert "radius-toggle-btn" in empty_code

    # 3. Budget-specific buttons for all 3 budget levels
    assert "Widen Budget to Medium/High" in empty_code
    assert "Widen Budget to High" in empty_code
    assert "Explore All Budgets" in empty_code

    # 4. Optional nearby search button contract
    assert "btn-search-nearby-locations" in empty_code
    assert "Search Nearby Locations (within 10 km)" in empty_code
    assert "onSearchNearby" in empty_code
    assert "hasEligibleNearby" in empty_code

    # 5. RecommendPage handles search nearby and distance
    assert "handleSearchNearby" in rec_code
    assert "formatRelaxationNotice" in rec_code


# ============================================================================
# 4. Targeted Requirement Verification Tests
# ============================================================================

def test_strict_btm_search_returns_no_restaurants_from_other_neighbourhoods():
    """
    Req 1: Strict BTM search returns only restaurants whose neighborhood is BTM.
    Never returns restaurants from Koramangala 5th Block or Jayanagar.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)
    pref = Preference(
        location="BTM",
        budget="medium",
        cuisine="Biryani",
        min_rating=4.0,
        include_nearby=False,
    )
    res = service.recommend(pref)
    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    assert res.relaxed_filters == []
    for item in res.recommendations:
        assert item.neighborhood == "BTM"
        assert item.neighborhood != "Koramangala 5th Block"
        assert item.neighborhood != "Jayanagar"


def test_nearby_locations_not_included_before_user_requests_them():
    """
    Req 1 & 4: When strict search yields 0 matches, nearby locations are NOT
    automatically returned until the user explicitly requests them.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)
    # Assamese low budget has 0 spots in Indiranagar
    pref = Preference(
        location="Indiranagar",
        budget="low",
        cuisine="Assamese",
        include_nearby=False,
    )
    res = service.recommend(pref)
    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert res.relaxed_filters == []


def test_clicking_nearby_button_searches_with_filters_preserved():
    """
    Req 5: On explicit user action (include_nearby=True), searches eligible alternative
    neighbourhoods within 10 km while strictly preserving cuisine, budget, min_rating.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)
    pref = Preference(
        location="Indiranagar",
        budget="low",
        cuisine="Assamese",
        include_nearby=True,
    )
    res = service.recommend(pref)
    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    for item in res.recommendations:
        assert item.neighborhood != "Indiranagar"
        assert item.distance_km is not None
        assert 0.0 < item.distance_km <= 10.0
        assert item.estimated_cost is not None and item.estimated_cost <= 400
        assert any("assamese" in c.lower() for c in item.cuisines)


def test_explicit_nearby_from_newly_verified_locations_preserves_filters():
    """
    Asserts that newly verified locations (e.g. BTM, ITPL Main Road) can expand
    to nearby neighbourhoods while preserving cuisine, budget, and rating constraints.
    """
    store = CatalogStore()
    service = RecommendService(store=store, enable_cache=False)

    # 1. BTM with low budget + Assamese (0 spots in BTM strictly -> expands to nearby within 10 km)
    pref_btm = Preference(
        location="BTM",
        budget="low",
        cuisine="Assamese",
        include_nearby=True,
    )
    res_btm = service.recommend(pref_btm)
    assert res_btm.candidate_count > 0
    assert len(res_btm.recommendations) > 0
    assert any("location_expanded" in f for f in res_btm.relaxed_filters)
    for r in res_btm.recommendations:
        assert any("assamese" in c.lower() for c in r.cuisines)
        assert r.estimated_cost is not None and r.estimated_cost <= 400
        assert r.distance_km is not None and 0.0 < r.distance_km <= 10.0

    # 2. ITPL Main Road, Whitefield with low budget + Continental
    pref_itpl = Preference(
        location="ITPL Main Road, Whitefield",
        budget="low",
        cuisine="Continental",
        include_nearby=True,
    )
    res_itpl = service.recommend(pref_itpl)
    assert res_itpl.candidate_count > 0
    for r in res_itpl.recommendations:
        assert any("continental" in c.lower() for c in r.cuisines)
        assert r.estimated_cost is not None and r.estimated_cost <= 400
        if r.neighborhood != "ITPL Main Road, Whitefield":
            assert r.distance_km is not None and 0.0 < r.distance_km <= 10.0

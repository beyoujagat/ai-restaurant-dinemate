"""
Phase 7 Resilience Tests:
1. Filter relaxation when shortlist is empty (drop extras first, widen budget by one band).
2. Forced LLM failure fallback to heuristic.
3. In-memory caching for repeated queries.
4. Preserving the original query without silent modification.
"""

from unittest.mock import MagicMock
import pytest

from app.catalog.store import CatalogStore
from app.domain.models import Preference, Restaurant
from app.services.recommend import RecommendService
from tests.fixtures.sample_catalog import FIXTURE_RESTAURANTS


def test_relaxation_drops_extras_first():
    """
    When candidate shortlist is empty with extras specified,
    relaxation drops extras first, returning matching candidates with relaxed_filters=['extras'].
    The original query in response.query must NOT be modified.
    """
    service = RecommendService(enable_cache=False)

    # In Banashankari, high budget (>=801) has 0 "quick bite" venues, but 12 general high-budget venues
    pref = Preference(
        location="Banashankari",
        budget="high",
        extras="quick bite",
    )

    res = service.recommend(pref)

    # Must return results after dropping extras
    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    assert "extras" in res.relaxed_filters
    # Original query remains untouched
    assert res.query.extras == "quick bite"
    assert res.query.budget == "high"


def test_relaxation_widens_budget_by_one_band():
    """
    When candidate shortlist is empty for a budget band, the initial search does NOT
    silently widen budget. It returns candidate_count=0 and an honest empty list,
    letting the user choose via the budget action in the EmptyState.
    """
    service = RecommendService()

    # Mock store to simulate:
    # - Strict query (low budget) -> 0 candidates
    # - Widened query (medium budget) -> candidates found!
    mock_store = MagicMock(spec=CatalogStore)

    def side_effect(pref, limit=None):
        if pref.budget == "low":
            return [], {"initial": 20, "sent_to_llm": 0}
        elif pref.budget == "medium":
            return FIXTURE_RESTAURANTS[:5], {"initial": 20, "sent_to_llm": 5}
        return [], {"initial": 20, "sent_to_llm": 0}

    mock_store.query_candidates.side_effect = side_effect
    service = RecommendService(store=mock_store, enable_cache=False)

    pref = Preference(
        location="Banashankari",
        budget="low",
        cuisine="North Indian",
    )

    res = service.recommend(pref)

    # Initial search must NOT silently widen budget
    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert res.relaxed_filters == []
    # Original query still says low
    assert res.query.budget == "low"


def test_relaxation_never_downgrades_high_budget_to_medium():
    """
    When no candidates exist for high / premium budget, relaxation must NOT
    fall back to medium budget. It must return candidate_count=0 and an honest empty list.
    """
    mock_store = MagicMock(spec=CatalogStore)

    def side_effect(pref, limit=None):
        if pref.budget == "high":
            return [], {"initial": 20, "sent_to_llm": 0}
        elif pref.budget == "medium":
            return FIXTURE_RESTAURANTS[:5], {"initial": 20, "sent_to_llm": 5}
        return [], {"initial": 20, "sent_to_llm": 0}

    mock_store.query_candidates.side_effect = side_effect
    service = RecommendService(store=mock_store, enable_cache=False)

    pref = Preference(
        location="Banashankari",
        budget="high",
        cuisine="Cafe",
    )

    res = service.recommend(pref)

    # Must NOT relax to medium; must return honest empty list
    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert "budget" not in res.relaxed_filters
    assert res.query.budget == "high"


def test_real_catalog_high_budget_no_fallback_to_medium():
    """
    In the real catalog, searching for Cafe in Central Bangalore (broad area, no expansion)
    with high budget has 0 candidates and must return empty recommendations rather than medium cafes.
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(
        location="Central Bangalore",
        budget="high",
        cuisine="Cafe",
        min_rating=4.0,
    )
    res = service.recommend(pref)
    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert "budget" not in res.relaxed_filters
    assert res.query.budget == "high"


def test_relaxation_both_extras_and_budget():
    """
    When both extras and tight budget are over-constrained,
    initial search does not silently widen budget. If initial search fails,
    candidate_count is 0.
    """
    mock_store = MagicMock(spec=CatalogStore)

    def side_effect(pref, limit=None):
        # Only matches if extras is None AND budget is medium
        if pref.extras is None and pref.budget == "medium":
            return FIXTURE_RESTAURANTS[:3], {"initial": 20, "sent_to_llm": 3}
        return [], {"initial": 20, "sent_to_llm": 0}

    mock_store.query_candidates.side_effect = side_effect
    service = RecommendService(store=mock_store, enable_cache=False)

    pref = Preference(
        location="Banashankari",
        budget="low",
        cuisine="North Indian",
        extras="impossible_decor",
    )

    res = service.recommend(pref)

    # Initial search must not silently widen budget
    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert "budget" not in res.relaxed_filters
    # Original query intact
    assert res.query.extras == "impossible_decor"
    assert res.query.budget == "low"


def test_overconstrained_impossible_query_honest_empty():
    """
    When even after all relaxations, no restaurants match,
    returns candidate_count=0, empty recommendations list, and helpful suggestions.
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(
        location="AtlantisUnderwaterCity999",
        budget="medium",
        cuisine="MermaidKelpHotpot",
    )

    res = service.recommend(pref)

    assert res.candidate_count == 0
    assert len(res.recommendations) == 0
    assert "No restaurants matched" in res.summary
    assert res.source == "heuristic"


def test_forced_llm_failure_returns_200_heuristic():
    """
    When LLM client throws an exception, times out, or returns invalid JSON,
    RecommendService gracefully falls back to heuristic ranking without crashing.
    """
    import app.llm.client as llm_client

    # Force complete_json to raise an unhandled network error
    def broken_llm(*args, **kwargs):
        raise ConnectionError("Simulated LLM network timeout")

    service = RecommendService(enable_cache=False)
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )

    # Monkeypatch complete_json in service module
    import app.services.recommend as rec_module
    original_complete = getattr(rec_module, "complete_json", None)

    try:
        # recommend_llm imports complete_json from app.llm.client
        import sys
        llm_mod = sys.modules["app.llm.client"]
        monkeypatch_target = getattr(llm_mod, "complete_json")
        llm_mod.complete_json = broken_llm

        res = service.recommend(pref)

        # Must fall back to heuristic
        assert res.source == "heuristic"
        assert res.candidate_count > 0
        assert len(res.recommendations) > 0
        assert "matches" in res.recommendations[0].explanation
    finally:
        llm_mod.complete_json = monkeypatch_target


def test_in_memory_demo_cache():
    """
    Calling recommend with identical preferences serves from in-memory cache.
    """
    service = RecommendService(enable_cache=True)
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )

    res1 = service.recommend(pref)
    assert len(service._cache) == 1

    # Second call uses cache
    res2 = service.recommend(pref)
    assert res2.summary == res1.summary
    assert len(res2.recommendations) == len(res1.recommendations)

    # Clear cache works
    service.clear_cache()
    assert len(service._cache) == 0


def test_ui_copy_for_both_banners():
    """
    Phase 7 exit criteria: Verify that the UI source file includes
    copy for both the relaxed filters banner and the heuristic mode banner,
    as well as error toast handling.
    """
    from pathlib import Path

    # Resolve frontend RecommendPage.tsx path relative to repo root
    repo_root = Path(__file__).resolve().parents[2]
    ui_page = repo_root / "frontend" / "src" / "pages" / "RecommendPage.tsx"

    assert ui_page.exists(), f"Frontend file missing at {ui_page}"
    content = ui_page.read_text(encoding="utf-8")

    # 1. Banner for relaxed filters
    assert "relaxed-notice-banner" in content
    assert "Note: To find great matches, some constraints were broadened" in content

    # 2. Notice when source === 'heuristic'
    assert "heuristic-notice-banner" in content
    assert "Catalog Heuristic Ranking Active" in content

    # 3. API/network error toast
    assert "api-error-toast" in content
    assert "Connection Issue" in content


def test_step5_frontend_empty_state_and_relaxation_copy():
    """
    Step 5 verification:
    1. RecommendPage.tsx implements formatRelaxationNotice handling 5km/10km/budget/extras.
    2. EmptyState.tsx removes hardcoded foodie hubs (Koramangala/Indiranagar/Jayanagar).
    3. EmptyState.tsx incorporates dynamic budget logic and verified nearby locations within 5km/10km.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    rec_page = repo_root / "frontend" / "src" / "pages" / "RecommendPage.tsx"
    empty_comp = repo_root / "frontend" / "src" / "components" / "EmptyState.tsx"

    assert rec_page.exists()
    assert empty_comp.exists()

    rec_content = rec_page.read_text(encoding="utf-8")
    empty_content = empty_comp.read_text(encoding="utf-8")

    # Step 5 notice formatter
    assert "formatRelaxationNotice" in rec_content
    assert "location_expanded_5km" in rec_content
    assert "location_expanded_10km" in rec_content
    assert "expanded your search within 5 km" in rec_content
    assert "expanded your search within 10 km" in rec_content
    assert "widened your budget criteria" in rec_content
    assert "relaxed optional amenity filters" in rec_content

    # Hard-coded hub suggestions removed from EmptyState
    assert "Try nearby foodie hubs like <strong>Koramangala</strong>" not in empty_content
    assert "Koramangala, Indiranagar, or Jayanagar" not in empty_content

    # Dynamic budget and nearby neighbourhood logic in EmptyState
    assert "fetchNearbyNeighbourhoods" in empty_content
    assert "radiusKm" in empty_content
    assert "nearby_5km" in empty_content
    assert "nearby_10km" in empty_content
    assert "btn-nearby-chip" in empty_content
    assert "Widen Budget to Medium/High" in empty_content
    assert "Widen Budget to High" in empty_content
    assert "Explore All Budgets" in empty_content


# ============================================================================
# Step 4: Geo-Proximity Relaxation Ladder Tests
# ============================================================================

def test_relaxation_ladder_geo_before_budget():
    """
    Zero candidates in strict location returns 0 candidates on initial search (include_nearby=False).
    When user explicitly requests nearby search (include_nearby=True), it searches within 10 km
    while preserving strict budget and cuisine.
    """
    service = RecommendService(enable_cache=False)
    pref_initial = Preference(
        location="Banashankari",
        budget="high",
        cuisine="Cafe",
        min_rating=4.0,
        include_nearby=False,
    )
    res_initial = service.recommend(pref_initial)
    assert res_initial.candidate_count == 0
    assert len(res_initial.recommendations) == 0

    pref = Preference(
        location="Banashankari",
        budget="high",
        cuisine="Cafe",
        min_rating=4.0,
        include_nearby=True,
    )
    res = service.recommend(pref)

    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    assert res.relaxed_filters in (["location_expanded_5km"], ["location_expanded_10km"])
    assert "within" in res.summary and "of Banashankari" in res.summary
    assert res.query.budget == "high"
    # Ensure recommended restaurants reflect actual locality in explanations
    for rec in res.recommendations:
        assert rec.estimated_cost is not None and rec.estimated_cost >= 801
        assert rec.distance_km is not None


def test_relaxation_ladder_10km_expansion():
    """
    Initial search returns 0 candidates when absent locally (include_nearby=False).
    When user explicitly requests nearby search (include_nearby=True), triggers 10 km expansion.
    E.g. In Domlur, Afghani cuisine is absent locally and within 5 km, but 3 venues
    exist within 10 km. Returns relaxed_filters=['location_expanded_10km'].
    """
    service = RecommendService(enable_cache=False)
    pref_initial = Preference(
        location="Domlur",
        cuisine="Afghani",
        include_nearby=False,
    )
    res_initial = service.recommend(pref_initial)
    assert res_initial.candidate_count == 0
    assert len(res_initial.recommendations) == 0

    pref = Preference(
        location="Domlur",
        cuisine="Afghani",
        include_nearby=True,
    )
    res = service.recommend(pref)

    assert res.candidate_count > 0
    assert len(res.recommendations) > 0
    assert res.relaxed_filters == ["location_expanded_10km"]
    assert "within 10 km of Domlur" in res.summary
    for rec in res.recommendations:
        assert rec.distance_km is not None


def test_relaxation_ladder_extras_before_geo():
    """
    Missing extra tag in strict location drops tag (Tier 1) before expanding radius.
    E.g. In Banashankari, high budget with 'quick bite' has 0 results.
    Dropping 'quick bite' in strict Banashankari finds 12 candidates locally,
    so it should NOT expand to 5 km.
    """
    service = RecommendService(enable_cache=False)
    pref = Preference(
        location="Banashankari",
        budget="high",
        extras="quick bite",
    )
    res = service.recommend(pref)

    assert res.candidate_count > 0
    assert res.relaxed_filters == ["extras"]
    assert "location_expanded_5km" not in res.relaxed_filters
    assert "location_expanded_10km" not in res.relaxed_filters


def test_relaxed_filters_all_tiers_mock():
    """
    Unit test using controlled mock store to verify exact relaxed_filters flag values
    across tiers of the relaxation ladder:
      - Strict / Tier 0: []
      - Tier 1: ["extras"]
      - Explicit nearby (include_nearby=True):
        Tier 2: ["location_expanded_5km"]
        Tier 3: ["location_expanded_5km", "extras"]
        Tier 5: ["location_expanded_10km", "extras"]
    """
    sample_rest_5km = [r.model_copy(update={"neighborhood": "Domlur"}) for r in FIXTURE_RESTAURANTS[:2]]
    sample_rest_10km = [r.model_copy(update={"neighborhood": "Bannerghatta Road"}) for r in FIXTURE_RESTAURANTS[:2]]

    # Test Tier 2: 5 km expansion with strict extras (with include_nearby=True)
    mock_store_t2 = MagicMock(spec=CatalogStore)
    def se_t2(pref, limit=None, locations=None):
        if locations and "Domlur" in locations:
            return sample_rest_5km, {"initial": 2, "sent_to_llm": 2}
        return [], {"initial": 0, "sent_to_llm": 0}
    mock_store_t2.query_candidates.side_effect = se_t2

    service_t2 = RecommendService(store=mock_store_t2, enable_cache=False)
    pref_t2 = Preference(location="Indiranagar", budget="low", cuisine="Italian", include_nearby=True)
    res_t2 = service_t2.recommend(pref_t2)
    assert res_t2.relaxed_filters == ["location_expanded_5km"]

    # Test Tier 3: 5 km expansion + drop extras (with include_nearby=True)
    mock_store_t3 = MagicMock(spec=CatalogStore)
    def se_t3(pref, limit=None, locations=None):
        if locations and "Domlur" in locations and pref.extras is None:
            return sample_rest_5km, {"initial": 2, "sent_to_llm": 2}
        return [], {"initial": 0, "sent_to_llm": 0}
    mock_store_t3.query_candidates.side_effect = se_t3

    service_t3 = RecommendService(store=mock_store_t3, enable_cache=False)
    pref_t3 = Preference(location="Indiranagar", budget="low", cuisine="Italian", extras="impossible_tag", include_nearby=True)
    res_t3 = service_t3.recommend(pref_t3)
    assert res_t3.relaxed_filters == ["location_expanded_5km", "extras"]

    # Test Tier 5: 10 km expansion + drop extras (with include_nearby=True)
    mock_store_t5 = MagicMock(spec=CatalogStore)
    def se_t5(pref, limit=None, locations=None):
        # Only matches when 10km radius queried (>40 locations) and extras dropped
        if locations and len(locations) > 40 and pref.extras is None:
            return sample_rest_10km, {"initial": 2, "sent_to_llm": 2}
        return [], {"initial": 0, "sent_to_llm": 0}
    mock_store_t5.query_candidates.side_effect = se_t5

    service_t5 = RecommendService(store=mock_store_t5, enable_cache=False)
    pref_t5 = Preference(location="Indiranagar", budget="low", cuisine="Italian", extras="impossible_tag", include_nearby=True)
    res_t5 = service_t5.recommend(pref_t5)
    assert res_t5.relaxed_filters == ["location_expanded_10km", "extras"]


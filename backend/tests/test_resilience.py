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
    When no candidates exist for a tight budget (e.g. low budget in a location where
    a cuisine is only available in medium budget), relaxation widens budget by one band.
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

    assert res.candidate_count == 5
    assert len(res.recommendations) == 5
    assert "budget" in res.relaxed_filters
    # Original query still says low
    assert res.query.budget == "low"


def test_relaxation_both_extras_and_budget():
    """
    When both extras and tight budget are over-constrained,
    relaxation drops extras AND widens budget, recording both in relaxed_filters.
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

    assert res.candidate_count == 3
    assert len(res.recommendations) == 3
    assert "extras" in res.relaxed_filters
    assert "budget" in res.relaxed_filters
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


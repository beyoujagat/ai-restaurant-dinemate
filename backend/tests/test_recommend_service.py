"""
Unit and integration tests for Phase 3:
RecommendService heuristic recommendation engine.
"""

from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from app.catalog.store import CatalogStore
from app.domain.models import Preference
from app.services.recommend import RecommendService
from tests.fixtures.sample_catalog import FIXTURE_RESTAURANTS


# ============================================================================
# 1. Validation Tests
# ============================================================================

def test_validation_errors_in_recommend():
    service = RecommendService()

    # Invalid budget
    with pytest.raises(ValidationError):
        service.recommend({"location": "Banashankari", "budget": "ultra_budget"})

    # Negative rating
    with pytest.raises(ValidationError):
        service.recommend({"location": "Banashankari", "min_rating": -1.0})

    # Rating > 5.0
    with pytest.raises(ValidationError):
        service.recommend({"location": "Banashankari", "min_rating": 5.5})


# ============================================================================
# 2. Fixture-Based Ordering and Response Structure Tests
# ============================================================================

def test_heuristic_top_5_ordering_with_mock_store():
    # Create a mock CatalogStore returning FIXTURE_RESTAURANTS
    mock_store = MagicMock(spec=CatalogStore)
    # Return 10 matching restaurants
    mock_store.query_candidates.return_value = (
        FIXTURE_RESTAURANTS[:10],
        {"initial": 25, "sent_to_llm": 10},
    )

    service = RecommendService(store=mock_store)
    pref = Preference(location="Banashankari", budget="medium")
    res = service.recommend(pref, result_limit=5)

    # Candidate count preserved from store
    assert res.candidate_count == 10

    # Output strictly capped at result_limit (5)
    assert len(res.recommendations) == 5

    # Check rank progression
    for i, rec in enumerate(res.recommendations, start=1):
        assert rec.rank == i

    # Source is heuristic
    assert res.source == "heuristic"
    assert res.relaxed_filters == []
    assert len(res.summary) > 0


def test_response_required_display_fields():
    """
    Problem statement requires 5 visible fields:
    name, cuisine, rating, estimated cost, AI/heuristic explanation.
    """
    mock_store = MagicMock(spec=CatalogStore)
    mock_store.query_candidates.return_value = (
        [FIXTURE_RESTAURANTS[0]],  # Jalsa
        {"initial": 25, "sent_to_llm": 1},
    )

    service = RecommendService(store=mock_store)
    pref = Preference(location="Banashankari", budget="medium", cuisine="North Indian")
    res = service.recommend(pref)

    assert len(res.recommendations) == 1
    rec = res.recommendations[0]

    # Required field assertions
    assert rec.name == "Jalsa"
    assert "North Indian" in rec.cuisines
    assert rec.rating == 4.1
    assert rec.estimated_cost == 800
    assert "Jalsa matches North Indian in Banashankari" in rec.explanation
    assert "~₹800 for two" in rec.explanation
    assert rec.neighborhood == "Banashankari"
    assert rec.url == "https://www.zomato.com/bangalore/jalsa-banashankari"


def test_empty_filters_no_crash():
    mock_store = MagicMock(spec=CatalogStore)
    mock_store.query_candidates.return_value = ([], {"initial": 25, "sent_to_llm": 0})

    service = RecommendService(store=mock_store)
    pref = Preference(location="Nowhere", cuisine="MartianFood")
    res = service.recommend(pref)

    assert res.candidate_count == 0
    assert res.recommendations == []
    assert "No restaurants matched" in res.summary
    assert res.source == "heuristic"


def test_template_explanation_format():
    service = RecommendService()
    rest = FIXTURE_RESTAURANTS[0]
    pref = Preference(location="Banashankari", cuisine="North Indian")

    exp = service.build_template_explanation(rest, pref)
    expected = "Jalsa matches North Indian in Banashankari with rating 4.1 and ~₹800 for two."
    assert exp == expected


# ============================================================================
# 3. Full Catalog Integration Test
# ============================================================================

def test_recommend_service_with_real_catalog():
    service = RecommendService()
    pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )

    res = service.recommend(pref)

    # Asserts
    assert res.source == "heuristic"
    assert res.candidate_count >= 1
    assert len(res.recommendations) <= 5
    assert len(res.recommendations) > 0

    # Check top recommendation
    top_rec = res.recommendations[0]
    assert top_rec.rank == 1
    assert top_rec.rating is not None and top_rec.rating >= 4.0
    assert top_rec.estimated_cost is not None and 401 <= top_rec.estimated_cost <= 800
    assert any("north indian" in c.lower() for c in top_rec.cuisines)
    assert "matches" in top_rec.explanation

    # Serializes cleanly to JSON dictionary
    data = res.model_dump()
    assert data["source"] == "heuristic"
    assert "recommendations" in data
    assert len(data["recommendations"]) == len(res.recommendations)

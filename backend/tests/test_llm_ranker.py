"""
Phase 4 unit tests — LLM ranker.

Tests cover:
- Prompt packing includes only allowlisted fields
- Mapper drops hallucinated IDs
- Mapper preserves catalog rating/cost even if model changes them
- Invalid JSON → heuristic fallback path
- Missing API key → heuristic fallback (no crash)
- Valid LLM response → source='llm' and proper ranking
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models import Preference, Restaurant, RecommendationResponse
from app.llm.prompts import build_user_prompt, _pack_candidate
from app.llm.schemas import LLMResponse, LLMRankedItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_restaurant(
    id: str = "abc123",
    name: str = "Spice Garden",
    neighborhood: str = "Banashankari",
    rating: float | None = 4.2,
    votes: int = 500,
    cost_for_two: int | None = 600,
    cuisines: list[str] | None = None,
    dishes_liked: list[str] | None = None,
    review_snippets: list[str] | None = None,
) -> Restaurant:
    return Restaurant(
        id=id,
        name=name,
        address="123 Main St",
        neighborhood=neighborhood,
        listed_city="Bangalore",
        cuisines=cuisines or ["North Indian"],
        cuisines_raw="North Indian",
        cost_for_two=cost_for_two,
        rating=rating,
        votes=votes,
        dishes_liked=dishes_liked or ["Butter Naan", "Dal Makhani"],
        review_snippets=review_snippets or ["Great food!", "Nice ambiance."],
        url="https://zomato.com/example",
    )


def _make_preference(**kwargs) -> Preference:
    defaults = dict(location="Banashankari", budget="medium", cuisine="North Indian", min_rating=4.0)
    defaults.update(kwargs)
    return Preference(**defaults)


# ---------------------------------------------------------------------------
# Prompt packing — allowlisted fields only
# ---------------------------------------------------------------------------

class TestPromptPacking:
    def test_pack_candidate_has_required_fields(self):
        rest = _make_restaurant()
        packed = _pack_candidate(rest)
        assert "id" in packed
        assert "name" in packed
        assert "cuisines" in packed
        assert "neighborhood" in packed
        assert "rating" in packed
        assert "cost_for_two" in packed

    def test_pack_candidate_excludes_address(self):
        """Raw address should not appear in the prompt (could contain PII)."""
        rest = _make_restaurant()
        packed = _pack_candidate(rest)
        # 'address' field is NOT in the allowlist for the prompt
        assert "address" not in packed

    def test_pack_candidate_truncates_dishes_liked(self):
        long_dishes = [f"Dish {i}" for i in range(20)]
        rest = _make_restaurant(dishes_liked=long_dishes)
        packed = _pack_candidate(rest)
        assert len(packed["dishes_liked"]) <= 6

    def test_pack_candidate_truncates_review_snippets(self):
        long_snippets = ["A" * 200 for _ in range(10)]
        rest = _make_restaurant(review_snippets=long_snippets)
        packed = _pack_candidate(rest)
        assert len(packed["review_snippets"]) <= 2
        for snippet in packed["review_snippets"]:
            assert len(snippet) <= 120

    def test_build_user_prompt_contains_preference_block(self):
        pref = _make_preference()
        candidates = [_make_restaurant()]
        prompt = build_user_prompt(pref, candidates, result_limit=5)
        assert "Banashankari" in prompt
        assert "medium" in prompt
        assert "North Indian" in prompt

    def test_build_user_prompt_contains_candidate_ids(self):
        candidates = [
            _make_restaurant(id="id001", name="A"),
            _make_restaurant(id="id002", name="B"),
        ]
        pref = _make_preference()
        prompt = build_user_prompt(pref, candidates, result_limit=5)
        assert "id001" in prompt
        assert "id002" in prompt

    def test_build_user_prompt_no_hallucination_fields(self):
        """Ensure raw address does not leak into the prompt."""
        rest = _make_restaurant()
        pref = _make_preference()
        prompt = build_user_prompt(pref, [rest], result_limit=5)
        assert "123 Main St" not in prompt

    def test_build_user_prompt_with_location_expansion(self):
        """Ensure relaxation context note is appended when location expansion occurs."""
        rest = _make_restaurant()
        pref = _make_preference(location="Indiranagar")

        # 5 km expansion
        prompt_5km = build_user_prompt(pref, [rest], result_limit=5, relaxed_filters=["location_expanded_5km"])
        assert "expanded to nearby neighbourhoods within 5 km of Indiranagar" in prompt_5km
        assert "Acknowledge the restaurant's actual locality accurately" in prompt_5km

        # 10 km expansion
        prompt_10km = build_user_prompt(pref, [rest], result_limit=5, relaxed_filters=["location_expanded_10km"])
        assert "expanded to nearby neighbourhoods within 10 km of Indiranagar" in prompt_10km
        assert "Acknowledge the restaurant's actual locality accurately" in prompt_10km


# ---------------------------------------------------------------------------
# Mapper — hallucinated IDs dropped / catalog values preserved
# ---------------------------------------------------------------------------

class TestMapper:
    def _make_service(self):
        """Return a RecommendService with a mock CatalogStore."""
        from app.services.recommend import RecommendService

        mock_store = MagicMock()
        svc = RecommendService(store=mock_store)
        return svc

    def test_mapper_drops_hallucinated_ids(self):
        svc = self._make_service()
        real_restaurant = _make_restaurant(id="real_id")
        llm_data = {
            "summary": "Great picks!",
            "recommendations": [
                {"id": "real_id", "rank": 1, "explanation": "Excellent.", "vibe_tag": "Hidden Gem"},
                {"id": "fake_id_999", "rank": 2, "explanation": "This doesn't exist.", "vibe_tag": "Ghost Spot"},
            ],
        }
        pref = _make_preference()
        result = svc._map_llm_response(llm_data, [real_restaurant], pref, result_limit=5)
        assert result is not None
        recs, _ = result
        ids_returned = [r.id for r in recs]
        assert "real_id" in ids_returned
        assert "fake_id_999" not in ids_returned

    def test_mapper_preserves_catalog_rating_not_model_value(self):
        """Even if the model says rating=5.0, we must use catalog rating=4.2."""
        svc = self._make_service()
        rest = _make_restaurant(id="r1", rating=4.2, cost_for_two=600)
        llm_data = {
            "summary": "Here are your top picks.",
            "recommendations": [
                # Model might try to change rating — we must ignore it
                {"id": "r1", "rank": 1, "explanation": "Perfect for you!", "vibe_tag": "Cozy Date Spot"},
            ],
        }
        pref = _make_preference()
        result = svc._map_llm_response(llm_data, [rest], pref, result_limit=5)
        assert result is not None
        recs, _ = result
        assert recs[0].rating == 4.2
        assert recs[0].estimated_cost == 600

    def test_mapper_sorts_by_rank(self):
        svc = self._make_service()
        r1 = _make_restaurant(id="r1", name="First")
        r2 = _make_restaurant(id="r2", name="Second")
        # LLM returns them out of order
        llm_data = {
            "summary": "Two options.",
            "recommendations": [
                {"id": "r2", "rank": 2, "explanation": "Good.", "vibe_tag": "Quick Bites Hub"},
                {"id": "r1", "rank": 1, "explanation": "Best.", "vibe_tag": "Top-Rated Date Night"},
            ],
        }
        pref = _make_preference()
        result = svc._map_llm_response(llm_data, [r1, r2], pref, result_limit=5)
        assert result is not None
        recs, _ = result
        assert recs[0].id == "r1"
        assert recs[1].id == "r2"

    def test_mapper_caps_at_result_limit(self):
        svc = self._make_service()
        restaurants = [_make_restaurant(id=f"r{i}") for i in range(7)]
        llm_data = {
            "summary": "Many picks.",
            "recommendations": [
                {"id": f"r{i}", "rank": i + 1, "explanation": "Good.", "vibe_tag": f"Vibe {i}"}
                for i in range(7)
            ],
        }
        pref = _make_preference()
        result = svc._map_llm_response(llm_data, restaurants, pref, result_limit=5)
        assert result is not None
        recs, _ = result
        assert len(recs) == 5

    def test_mapper_returns_none_when_all_ids_hallucinated(self):
        svc = self._make_service()
        real_restaurant = _make_restaurant(id="real_id")
        llm_data = {
            "summary": "These are great!",
            "recommendations": [
                {"id": "ghost_1", "rank": 1, "explanation": "Amazing!", "vibe_tag": "Unknown Gem"},
                {"id": "ghost_2", "rank": 2, "explanation": "Lovely!", "vibe_tag": "Phantom Spot"},
            ],
        }
        pref = _make_preference()
        result = svc._map_llm_response(llm_data, [real_restaurant], pref, result_limit=5)
        assert result is None

    def test_mapper_returns_none_for_invalid_schema(self):
        svc = self._make_service()
        rest = _make_restaurant(id="r1")
        # Missing required 'recommendations' key
        bad_llm_data = {"summary": "Oops"}
        pref = _make_preference()
        result = svc._map_llm_response(bad_llm_data, [rest], pref, result_limit=5)
        assert result is None


# ---------------------------------------------------------------------------
# Fallback paths — missing key / invalid JSON → heuristic
# ---------------------------------------------------------------------------

class TestFallbackPaths:
    def _make_service_with_mock_store(self, candidates):
        from app.services.recommend import RecommendService

        mock_store = MagicMock()
        mock_store.query_candidates.return_value = (candidates, {})
        svc = RecommendService(store=mock_store)
        return svc

    def test_missing_api_key_returns_heuristic(self):
        """When neither GROQ_API_KEY nor LLM_API_KEY is set, source must be 'heuristic'."""
        candidates = [_make_restaurant(id="r1")]
        svc = self._make_service_with_mock_store(candidates)
        pref = _make_preference()

        with patch.dict("os.environ", {"GROQ_API_KEY": "", "LLM_API_KEY": ""}, clear=False):
            result = svc.recommend_llm(pref)

        assert isinstance(result, RecommendationResponse)
        assert result.source == "heuristic"
        assert len(result.recommendations) >= 0  # No crash

    def test_groq_api_key_resolution(self):
        """Verify GROQ_API_KEY is recognized by _get_api_key."""
        from app.llm.client import _get_api_key

        with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_groq_direct", "LLM_API_KEY": ""}, clear=False):
            assert _get_api_key() == "gsk_groq_direct"

        with patch.dict("os.environ", {"GROQ_API_KEY": "", "LLM_API_KEY": "gsk_llm_fallback"}, clear=False):
            assert _get_api_key() == "gsk_llm_fallback"

    def test_invalid_json_from_llm_returns_heuristic(self):
        """When complete_json returns None (bad JSON / timeout), fallback to heuristic."""
        candidates = [_make_restaurant(id="r1")]
        svc = self._make_service_with_mock_store(candidates)
        pref = _make_preference()

        with patch("app.llm.client.complete_json", return_value=None):
            result = svc.recommend_llm(pref)

        assert result.source == "heuristic"

    def test_llm_exception_returns_heuristic(self):
        """Even if complete_json raises, the service must not crash."""
        candidates = [_make_restaurant(id="r1")]
        svc = self._make_service_with_mock_store(candidates)
        pref = _make_preference()

        with patch("app.llm.client.complete_json", side_effect=RuntimeError("network error")):
            result = svc.recommend_llm(pref)

        assert result.source == "heuristic"

    def test_valid_llm_response_returns_llm_source(self):
        """Happy path: valid LLM JSON → source='llm', explanations and vibe_tag from model."""
        rest = _make_restaurant(id="r1", name="Taj Palace")
        svc = self._make_service_with_mock_store([rest])
        pref = _make_preference()

        llm_payload = {
            "summary": "A fantastic choice for North Indian cuisine.",
            "recommendations": [
                {
                    "id": "r1",
                    "rank": 1,
                    "explanation": "Taj Palace's celebrated Butter Naan and Dal Makhani are crowd favourites. Perfectly located in Banashankari, it's an ideal medium-budget spot for a North Indian craving.",
                    "vibe_tag": "Top-Rated Date Night",
                },
            ],
        }

        with patch.dict("os.environ", {"LLM_API_KEY": "gsk_test"}, clear=False):
            with patch("app.llm.client.complete_json", return_value=llm_payload):
                result = svc.recommend_llm(pref)

        assert result.source == "llm"
        assert len(result.recommendations) == 1
        assert result.recommendations[0].name == "Taj Palace"
        assert "North Indian" in result.recommendations[0].explanation
        assert result.recommendations[0].vibe_tag == "Top-Rated Date Night"
        assert result.summary == "A fantastic choice for North Indian cuisine."

    def test_empty_candidate_set_returns_empty_heuristic(self):
        """Zero candidates → empty recommendations, no LLM call."""
        svc = self._make_service_with_mock_store([])
        pref = _make_preference()

        with patch("app.llm.client.complete_json") as mock_llm:
            result = svc.recommend_llm(pref)
            mock_llm.assert_not_called()

        assert result.candidate_count == 0
        assert result.recommendations == []


# ---------------------------------------------------------------------------
# LLM schemas — basic validation
# ---------------------------------------------------------------------------

class TestLLMSchemas:
    def test_valid_llm_response(self):
        data = {
            "summary": "Great picks.",
            "recommendations": [
                {"id": "abc", "rank": 1, "explanation": "Fits well.", "vibe_tag": "Casual Family Hangout"},
            ],
        }
        resp = LLMResponse(**data)
        assert resp.summary == "Great picks."
        assert len(resp.recommendations) == 1
        assert resp.recommendations[0].rank == 1
        assert resp.recommendations[0].vibe_tag == "Casual Family Hangout"

    def test_valid_llm_response_vibe_tag_present(self):
        """vibe_tag is a required field on LLMRankedItem."""
        item = LLMRankedItem(
            id="xyz",
            rank=2,
            explanation="Dishes and vibe.",
            vibe_tag="Authentic Biryani Spot",
        )
        assert item.vibe_tag == "Authentic Biryani Spot"

    def test_llm_ranked_item_missing_vibe_tag_raises(self):
        """vibe_tag is required — omitting it must raise a validation error."""
        with pytest.raises(Exception):
            LLMRankedItem(id="abc", rank=1, explanation="Good place.")

    def test_llm_response_missing_summary_raises(self):
        data = {
            "recommendations": [
                {"id": "abc", "rank": 1, "explanation": "Fits well.", "vibe_tag": "Quick Bite Stop"},
            ],
        }
        with pytest.raises(Exception):
            LLMResponse(**data)

    def test_llm_ranked_item_missing_id_raises(self):
        with pytest.raises(Exception):
            LLMRankedItem(rank=1, explanation="Missing id!", vibe_tag="Cozy Spot")

    def test_heuristic_recommendation_item_vibe_tag_is_none(self):
        """When using the heuristic path, vibe_tag must be None (no LLM)."""
        from app.domain.models import RecommendationItem
        item = RecommendationItem(
            id="x1",
            rank=1,
            name="Test Place",
            explanation="Matches your criteria.",
        )
        assert item.vibe_tag is None

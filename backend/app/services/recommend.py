"""
Recommendation Service (Phase 3 + 4).
Orchestrates candidate filtering, heuristic ranking, and LLM ranking.

Phase 3: Deterministic heuristic baseline.
Phase 4: LLM ranking via Groq (with automatic fallback to heuristic on any error).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.catalog.store import CatalogStore
from app.domain.models import (
    Preference,
    RecommendationItem,
    RecommendationResponse,
    Restaurant,
)

logger = logging.getLogger(__name__)

DEFAULT_RESULT_LIMIT = 5


def get_result_limit() -> int:
    try:
        return int(os.getenv("RESULT_LIMIT", str(DEFAULT_RESULT_LIMIT)))
    except (ValueError, TypeError):
        return DEFAULT_RESULT_LIMIT


class RecommendService:
    """
    Recommendation orchestration service.
    Phase 3: Deterministic heuristic recommendation engine.
    Phase 4: Integrates LLM (Groq) ranking with heuristic fallback.
    Phase 7: Resilience: filter relaxation policy, in-memory demo caching, honest empty states.
    """

    def __init__(
        self,
        store: CatalogStore | None = None,
        enable_cache: bool = True,
    ) -> None:
        self.store = store or CatalogStore()
        self.enable_cache = enable_cache
        self._cache: dict[tuple, RecommendationResponse] = {}

    def clear_cache(self) -> None:
        """Clear in-memory response cache."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Phase 7 — Candidate Relaxation Policy (architecture §8.2)
    # ------------------------------------------------------------------

    def get_candidates_with_relaxation(
        self,
        preference: Preference,
        candidate_limit: int | None = None,
    ) -> tuple[list[Restaurant], list[str], Preference]:
        """
        Phase 7: Relaxation policy when candidate shortlist is empty:
        1. Query candidates matching strict preferences.
        2. If 0 candidates and extras specified: drop extra tags first.
        3. If still 0 candidates: widen budget band by one step (e.g. low -> medium, medium -> high/low).
           Premium ('high') budget is never relaxed down to medium to protect the user's hard constraint.
        4. Return (candidates, relaxed_filters, effective_preference).
           Notice: original preference is never modified in the outer response.query.
        """
        from app.catalog.filters import get_candidate_limit

        limit = candidate_limit or get_candidate_limit()

        # 1. Primary strict candidate search
        candidates, _ = self.store.query_candidates(preference, limit)
        if candidates:
            return candidates, [], preference

        # 2. Step 1: Drop extra tags first
        if preference.extras:
            p_no_extras = preference.model_copy(update={"extras": None})
            cand_no_extras, _ = self.store.query_candidates(p_no_extras, limit)
            if cand_no_extras:
                logger.info("Shortlist empty: dropped extras filter '%s' -> %d candidates", preference.extras, len(cand_no_extras))
                return cand_no_extras, ["extras"], p_no_extras

        # 3. Step 2: Then widen budget by one band (low -> medium, medium -> high/low).
        # Premium ('high') budget searches never automatically fall back to medium.
        current_budget = (preference.budget or "").strip().lower()
        widened_budgets: list[str] = []
        if current_budget == "low":
            widened_budgets = ["medium"]
        elif current_budget == "medium":
            widened_budgets = ["high", "low"]
        elif current_budget == "high":
            widened_budgets = []

        for b in widened_budgets:
            # Try with original preference extras first
            if preference.extras:
                p_try = preference.model_copy(update={"budget": b})
                c_try, _ = self.store.query_candidates(p_try, limit)
                if c_try:
                    logger.info("Shortlist empty: widened budget (%s -> %s) -> %d candidates", current_budget, b, len(c_try))
                    return c_try, ["budget"], p_try

            # Try with extras dropped
            p_try_no_ext = preference.model_copy(update={"budget": b, "extras": None})
            c_try_no_ext, _ = self.store.query_candidates(p_try_no_ext, limit)
            if c_try_no_ext:
                filters_relaxed = ["extras", "budget"] if preference.extras else ["budget"]
                logger.info("Shortlist empty: relaxed %s -> %d candidates", filters_relaxed, len(c_try_no_ext))
                return c_try_no_ext, filters_relaxed, p_try_no_ext

        # 4. If all relaxations still yield 0 candidates, return empty
        return [], [], preference

    # ------------------------------------------------------------------
    # Phase 3 helpers
    # ------------------------------------------------------------------

    def build_template_explanation(
        self,
        restaurant: Restaurant,
        preference: Preference,
    ) -> str:
        """
        Generate deterministic template explanation matching architecture §8.5:
        '{name} matches {cuisine} in {location} with rating {rating} and ~₹{cost} for two.'
        """
        name = restaurant.name

        # Target cuisine or first available cuisine
        cuisine = preference.cuisine or (
            restaurant.cuisines[0] if restaurant.cuisines else "dining"
        )

        # Location: neighborhood or listed city or query location
        location = (
            restaurant.neighborhood
            or restaurant.listed_city
            or (preference.location or "Bangalore")
        )

        rating_str = (
            f"rating {restaurant.rating}"
            if restaurant.rating is not None
            else "newly opened"
        )

        cost_str = (
            f"~₹{restaurant.cost_for_two} for two"
            if restaurant.cost_for_two is not None
            else "unlisted budget"
        )

        return f"{name} matches {cuisine} in {location} with {rating_str} and {cost_str}."

    def build_summary(self, preference: Preference, rec_count: int) -> str:
        """
        Generate short 1-line summary matching architecture §8.6.
        """
        if rec_count == 0:
            loc = preference.location or "Bangalore"
            return f"No restaurants matched your criteria in {loc}. Try widening your budget or adjusting cuisine."

        cuisine_part = f"{preference.cuisine} " if preference.cuisine else ""
        location_part = f"in {preference.location}" if preference.location else "in Bangalore"
        return f"Top {rec_count} {cuisine_part}recommendations {location_part}."

    def recommend_heuristic(
        self,
        preference: Preference | dict[str, Any],
        result_limit: int | None = None,
        pre_filtered: tuple[list[Restaurant], list[str], Preference] | None = None,
    ) -> RecommendationResponse:
        """
        Deterministic heuristic recommendation flow (Phase 3 + Phase 7):
        1. Validate preferences
        2. Query candidates (with Phase 7 relaxation if initial query is empty)
        3. Slice top N (default 5)
        4. Rehydrate display fields strictly from the catalog
        5. Package into RecommendationResponse with source='heuristic'
        """
        # Validate inputs via Pydantic model
        if isinstance(preference, dict):
            pref = Preference(**preference)
        else:
            pref = preference

        limit = result_limit or get_result_limit()

        # Retrieve candidates (applying relaxation if empty)
        if pre_filtered is not None:
            candidates, relaxed_filters, effective_pref = pre_filtered
        else:
            candidates, relaxed_filters, effective_pref = self.get_candidates_with_relaxation(pref, limit)

        candidate_count = len(candidates)

        # Take top RESULT_LIMIT
        top_candidates = candidates[:limit]

        # Rehydrate display fields strictly from catalog
        recommendations: list[RecommendationItem] = []
        for rank, rest in enumerate(top_candidates, start=1):
            item = RecommendationItem(
                id=rest.id,
                rank=rank,
                name=rest.name,
                cuisines=rest.cuisines,
                rating=rest.rating,
                votes=rest.votes,
                estimated_cost=rest.cost_for_two,
                neighborhood=rest.neighborhood or rest.listed_city,
                explanation=self.build_template_explanation(rest, effective_pref),
                url=rest.url,
            )
            recommendations.append(item)

        summary = self.build_summary(pref, len(recommendations))

        return RecommendationResponse(
            query=pref,
            candidate_count=candidate_count,
            relaxed_filters=relaxed_filters,
            summary=summary,
            source="heuristic",
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Phase 4 — LLM ranking with heuristic fallback
    # ------------------------------------------------------------------

    def _map_llm_response(
        self,
        llm_data: dict[str, Any],
        candidates: list[Restaurant],
        preference: Preference,
        result_limit: int,
    ) -> tuple[list[RecommendationItem], str] | None:
        """
        Map raw LLM JSON to RecommendationItems.

        Rules:
        - Drop any IDs not present in the candidate set (hallucinations).
        - Sort by LLM-returned rank.
        - Rehydrate ALL catalog fields from SQLite (ignore any model-supplied rating/cost).
        - Return None if the LLM output is structurally invalid.
        """
        from app.llm.schemas import LLMResponse

        try:
            parsed = LLMResponse(**llm_data)
        except Exception as exc:
            logger.warning("LLM response failed Pydantic validation: %s", exc)
            return None

        # Build a quick lookup: id -> Restaurant
        catalog_by_id: dict[str, Restaurant] = {r.id: r for r in candidates}

        # Filter + sort by rank
        valid_items = [
            item for item in parsed.recommendations
            if item.id in catalog_by_id
        ]
        if not valid_items:
            logger.warning("LLM returned no valid IDs from the candidate set.")
            return None

        valid_items.sort(key=lambda x: x.rank)

        recommendations: list[RecommendationItem] = []
        for llm_item in valid_items[:result_limit]:
            rest = catalog_by_id[llm_item.id]
            vibe_tag = (llm_item.vibe_tag or "").strip() or None
            if not vibe_tag and rest.rest_types:
                vibe_tag = f"Authentic {rest.rest_types[0]}"
            recommendations.append(
                RecommendationItem(
                    id=rest.id,
                    rank=llm_item.rank,
                    name=rest.name,
                    cuisines=rest.cuisines,
                    # Always use catalog values, never model-supplied
                    rating=rest.rating,
                    votes=rest.votes,
                    estimated_cost=rest.cost_for_two,
                    neighborhood=rest.neighborhood or rest.listed_city,
                    explanation=llm_item.explanation,
                    vibe_tag=vibe_tag,
                    url=rest.url,
                )
            )

        return recommendations, parsed.summary

    def recommend_llm(
        self,
        preference: Preference | dict[str, Any],
        result_limit: int | None = None,
    ) -> RecommendationResponse:
        """
        LLM-backed recommendation flow (Phase 4 + Phase 7).
        Falls back to heuristic if:
          - LLM_API_KEY is missing
          - LLM returns invalid JSON
          - LLM times out
          - LLM hallucinates all IDs
          - Any other unexpected error
        """
        from app.llm.client import complete_json
        from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt

        if isinstance(preference, dict):
            pref = Preference(**preference)
        else:
            pref = preference

        limit = result_limit or get_result_limit()

        # Retrieve candidates with Phase 7 relaxation policy
        candidates, relaxed_filters, effective_pref = self.get_candidates_with_relaxation(pref, limit)
        candidate_count = len(candidates)

        if not candidates:
            # No candidates at all — return empty response immediately
            return RecommendationResponse(
                query=pref,
                candidate_count=0,
                relaxed_filters=[],
                summary=self.build_summary(pref, 0),
                source="heuristic",
                recommendations=[],
            )

        # Attempt LLM call — guard against any unexpected exception from the client
        user_prompt = build_user_prompt(effective_pref, candidates, result_limit=limit)
        try:
            llm_data = complete_json(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            logger.error("Unexpected exception calling LLM; falling back to heuristic: %s", exc)
            llm_data = None

        if llm_data is not None:
            mapped = self._map_llm_response(llm_data, candidates, effective_pref, limit)
            if mapped is not None:
                recommendations, llm_summary = mapped
                logger.info(
                    "LLM ranker succeeded: %d/%d candidates → %d results (relaxed=%s)",
                    candidate_count, candidate_count, len(recommendations), relaxed_filters,
                )
                return RecommendationResponse(
                    query=pref,
                    candidate_count=candidate_count,
                    relaxed_filters=relaxed_filters,
                    summary=llm_summary,
                    source="llm",
                    recommendations=recommendations,
                )

        # Fallback to heuristic
        logger.info("Falling back to heuristic ranker (LLM unavailable or invalid).")
        heuristic_resp = self.recommend_heuristic(
            pref,
            result_limit=limit,
            pre_filtered=(candidates, relaxed_filters, effective_pref),
        )
        return heuristic_resp

    def recommend(
        self,
        preference: Preference | dict[str, Any],
        result_limit: int | None = None,
    ) -> RecommendationResponse:
        """
        Primary recommendation entry point.
        Phase 4: Attempts LLM ranking; falls back to heuristic on any failure.
        Phase 7: Checks in-memory cache, executes relaxation policy if needed.
        """
        pref = Preference(**preference) if isinstance(preference, dict) else preference
        limit = result_limit or get_result_limit()

        cache_key = (
            pref.location,
            pref.budget,
            pref.cuisine,
            pref.min_rating,
            pref.extras,
            limit,
        )

        if self.enable_cache and cache_key in self._cache:
            logger.info("Serving recommendations from in-memory cache for %s", cache_key)
            return self._cache[cache_key].model_copy(deep=True)

        resp = self.recommend_llm(pref, result_limit=limit)

        if self.enable_cache and resp.recommendations:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = resp.model_copy(deep=True)

        return resp


if __name__ == "__main__":
    # Demo CLI run: python -m app.services.recommend
    service = RecommendService()
    sample_pref = Preference(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    res = service.recommend(sample_pref)

    print("\n" + "=" * 60)
    print("        DINEMATE RECOMMENDATION DEMO (PHASE 4)          ")
    print("=" * 60)
    print(f" Query:           {res.query.model_dump(exclude_none=True)}")
    print(f" Candidate Count: {res.candidate_count}")
    print(f" Source:          {res.source}")
    print(f" Summary:         {res.summary}")
    print("-" * 60)
    for rec in res.recommendations:
        cost_display = f"₹{rec.estimated_cost}" if rec.estimated_cost else "N/A"
        print(f" #{rec.rank} {rec.name} ({rec.neighborhood})")
        print(f"    Rating: {rec.rating}★ ({rec.votes} votes) | Cost for two: {cost_display}")
        print(f"    Cuisines: {', '.join(rec.cuisines)}")
        print(f"    Explanation: {rec.explanation}")
        if rec.url:
            print(f"    URL: {rec.url}")
        print()
    print("=" * 60 + "\n")

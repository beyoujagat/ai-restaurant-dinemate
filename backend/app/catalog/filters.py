"""
Candidate Filtering & Pre-Ranking Engine (Phase 2).
Implements the deterministic integration-layer filter as defined in
architecture §8.2 and implementation-plan Phase 2.

Filter Order:
  1. Location (neighborhood OR listed_city)
  2. Budget band (low / medium / high)
  3. Cuisine containment (case-insensitive)
  4. Minimum rating (excludes null ratings)
  5. Optional structured extras (quick bites, book_table, online_order, family-friendly)

Pre-ranking score:
  score = rating_or_0 * math.log(1 + votes) + keyword_boost
"""

from __future__ import annotations

import math
import os
import re
from typing import Sequence

from app.domain.budget import is_in_budget
from app.domain.models import Preference, Restaurant

# Default limit of candidates to pass forward to recommendation ranker
DEFAULT_CANDIDATE_LIMIT = 12


def get_candidate_limit() -> int:
    try:
        return int(os.getenv("CANDIDATE_LIMIT", str(DEFAULT_CANDIDATE_LIMIT)))
    except (ValueError, TypeError):
        return DEFAULT_CANDIDATE_LIMIT


# ============================================================================
# Individual Filter Functions
# ============================================================================

def filter_by_location(restaurants: Sequence[Restaurant], location: str | None) -> list[Restaurant]:
    """
    Match location against neighborhood OR listed_city (case-insensitive).
    """
    if not location or not location.strip():
        return list(restaurants)

    norm_loc = location.strip().lower()
    results: list[Restaurant] = []

    for r in restaurants:
        r_neigh = (r.neighborhood or "").strip().lower()
        r_city = (r.listed_city or "").strip().lower()

        # Match exact equality or containment
        if norm_loc == r_neigh or norm_loc == r_city:
            results.append(r)
        elif norm_loc in r_neigh or norm_loc in r_city:
            results.append(r)

    return results


def filter_by_budget(restaurants: Sequence[Restaurant], budget_band: str | None) -> list[Restaurant]:
    """
    Match approx_cost(for two) within low (<=400), medium (401-800), high (>=801).
    Restaurants with missing cost fail the filter if a budget band is specified.
    """
    if not budget_band or not budget_band.strip():
        return list(restaurants)

    band = budget_band.strip().lower()
    return [r for r in restaurants if is_in_budget(r.cost_for_two, band)]


def filter_by_cuisine(restaurants: Sequence[Restaurant], cuisine: str | None) -> list[Restaurant]:
    """
    Check if target cuisine is contained in restaurant's cuisine list (case-insensitive).
    """
    if not cuisine or not cuisine.strip():
        return list(restaurants)

    norm_c = cuisine.strip().lower()
    results: list[Restaurant] = []

    for r in restaurants:
        matched = False
        # Check parsed cuisine list
        for c in r.cuisines:
            if norm_c == c.lower() or norm_c in c.lower():
                matched = True
                break

        # Fallback check on raw cuisine string
        if not matched and r.cuisines_raw:
            if norm_c in r.cuisines_raw.lower():
                matched = True

        if matched:
            results.append(r)

    return results


def filter_by_min_rating(restaurants: Sequence[Restaurant], min_rating: float | None) -> list[Restaurant]:
    """
    Exclude restaurants below min_rating.
    Critically: exclude restaurants with null rating when min_rating is set.
    """
    if min_rating is None:
        return list(restaurants)

    return [r for r in restaurants if r.rating is not None and r.rating >= min_rating]


def filter_by_extras(restaurants: Sequence[Restaurant], extras: str | None) -> list[Restaurant]:
    """
    Optional structured matching on common user intent tags:
      - 'quick bites' / 'quick service' -> rest_type contains Quick Bites
      - 'table booking' / 'book table' -> book_table is True
      - 'online order' -> online_order is True
      - 'family-friendly' -> Casual Dining or Buffet, avoids Pubs and bars unless requested
    """
    if not extras or not extras.strip():
        return list(restaurants)

    text = extras.lower()
    filtered = list(restaurants)

    if "quick bite" in text or "quick service" in text or "fast food" in text:
        filtered = [
            r for r in filtered
            if any("quick bites" in t.lower() for t in r.rest_types)
        ]

    if "book table" in text or "table booking" in text or "reservation" in text:
        filtered = [r for r in filtered if r.book_table]

    if "online order" in text or "delivery" in text:
        filtered = [r for r in filtered if r.online_order]

    if "family" in text or "family-friendly" in text:
        # Prefer Casual Dining / Buffet, exclude Pubs and Bars if possible
        has_family_venues = [
            r for r in filtered
            if any(t.lower() in {"casual dining", "buffet"} for t in r.rest_types)
            and not any("pub" in t.lower() or "bar" in t.lower() for t in r.rest_types)
        ]
        if has_family_venues:
            filtered = has_family_venues

    return filtered


# ============================================================================
# Scoring and Pre-Ranking
# ============================================================================

def score_candidate(restaurant: Restaurant, extras: str | None = None) -> float:
    """
    Pre-ranking score formula:
      score = rating_or_0 * math.log(1 + votes) + keyword_boost
    """
    rating = restaurant.rating or 0.0
    votes = max(0, restaurant.votes)

    base_score = rating * math.log(1.0 + votes)

    # Optional keyword boost from dishes_liked / rest_types if extras text is given
    keyword_boost = 0.0
    if extras:
        keywords = [
            w for w in re.findall(r"\b[a-zA-Z]{3,}\b", extras.lower())
            if w not in {"with", "and", "the", "for", "any", "good", "place"}
        ]
        dishes_text = " ".join(restaurant.dishes_liked).lower()
        for kw in keywords:
            if kw in dishes_text:
                keyword_boost += 0.5

    return round(base_score + keyword_boost, 4)


# ============================================================================
# Complete Candidate Filter Pipeline
# ============================================================================

def apply_candidate_filters(
    restaurants: Sequence[Restaurant],
    preference: Preference,
    candidate_limit: int | None = None,
) -> tuple[list[Restaurant], dict[str, int]]:
    """
    Applies hard filters in order, calculates scores, and returns top candidates.
    Also returns stage count metrics for observability.
    """
    limit = candidate_limit or get_candidate_limit()
    counts: dict[str, int] = {"initial": len(restaurants)}

    # 1. Location filter
    stage = filter_by_location(restaurants, preference.location)
    counts["after_location"] = len(stage)

    # 2. Budget filter
    stage = filter_by_budget(stage, preference.budget)
    counts["after_budget"] = len(stage)

    # 3. Cuisine filter
    stage = filter_by_cuisine(stage, preference.cuisine)
    counts["after_cuisine"] = len(stage)

    # 4. Rating filter
    stage = filter_by_min_rating(stage, preference.min_rating)
    counts["after_rating"] = len(stage)

    # 5. Optional structured extras
    if preference.extras:
        stage = filter_by_extras(stage, preference.extras)
        counts["after_extras"] = len(stage)

    # Pre-rank by score
    scored_candidates = [
        (r, score_candidate(r, preference.extras))
        for r in stage
    ]
    # Sort descending by score, tie-break by votes then name
    scored_candidates.sort(key=lambda item: (item[1], item[0].votes, item[0].name), reverse=True)

    shortlist = [item[0] for item in scored_candidates[:limit]]
    counts["sent_to_llm"] = len(shortlist)

    return shortlist, counts

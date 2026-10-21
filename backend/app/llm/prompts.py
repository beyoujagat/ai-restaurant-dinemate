"""
LLM Prompt Builders (Phase 4).
Constructs system and user prompts for the Groq LLM ranker.

Design rules (from architecture §8.3):
- Only allowlisted catalog fields are included in the prompt.
- The model must rank only the IDs it receives; it must NOT invent names, ratings, or prices.
- Token budget is respected by truncating dishes_liked and review_snippets.
- The model is NOT asked about live wait times or "open now" status.
"""

from __future__ import annotations

from app.domain.models import Preference, Restaurant

# Maximum number of dish tags to include per restaurant (token budget)
MAX_DISHES = 6
# Maximum number of review snippets to include per restaurant (token budget)
MAX_SNIPPETS = 2
# Maximum characters per review snippet
MAX_SNIPPET_CHARS = 120

# Allowlist of fields sent to the LLM (never send phone, full menu, raw address)
_ALLOWED_FIELDS = {
    "id", "name", "cuisines_raw", "neighborhood", "listed_city",
    "rating", "votes", "cost_for_two", "rest_types", "listed_types",
    "online_order", "book_table", "dishes_liked", "review_snippets",
}

SYSTEM_PROMPT = """You are a Bangalore dining concierge — warm, knowledgeable, and vivid.

Your job: given a diner's preferences and a shortlist of pre-filtered restaurants,
rank the restaurants from most to least suitable and write a rich explanation for each.

STRICT RULES:
1. Rank ONLY the restaurant IDs you receive. Do NOT invent or add restaurants.
2. Do NOT modify, guess, or hallucinate ratings, prices, or names — use them only as context.
3. Do NOT claim information you do not have (e.g. live wait times, whether the place is open now).
4. Return valid JSON matching EXACTLY this schema:
{
  "summary": "<one sentence for the diner>",
  "recommendations": [
    {
      "id": "<exact id>",
      "rank": 1,
      "explanation": "<vivid 2-sentence rationale: sentence 1 mentions 1-2 signature dishes from dishes_liked (e.g. Mutton Seekh, Dim Sum, Craft Beer); sentence 2 explains how the restaurant fits the diner's location, budget, and vibe (e.g. date night, family gathering, casual hangout)>",
      "vibe_tag": "<concise AI badge, e.g. 'Top-Rated Date Night', 'Authentic Biryani Spot', 'Luxury Fine Dining', 'Casual Family Hangout', 'Craft Beer & Bites'>"
    },
    ...
  ]
}
5. All restaurants in the list must appear in recommendations unless there are fewer than requested.
6. Explanations MUST mention 1-2 dishes from the restaurant's dishes_liked list and reference the diner's location, budget tier, and vibe/extras.
7. vibe_tag must be 3-5 words, evocative, and capture the restaurant's personality.
"""


def _pack_candidate(restaurant: Restaurant) -> dict:
    """
    Return a compact dict containing only allowlisted fields for the prompt.
    Truncates dishes_liked and review_snippets for token economy.
    """
    dishes = restaurant.dishes_liked[:MAX_DISHES]
    snippets = [
        s[:MAX_SNIPPET_CHARS] for s in restaurant.review_snippets[:MAX_SNIPPETS]
    ]

    return {
        "id": restaurant.id,
        "name": restaurant.name,
        "cuisines": restaurant.cuisines_raw or ", ".join(restaurant.cuisines),
        "neighborhood": restaurant.neighborhood or restaurant.listed_city,
        "rating": restaurant.rating,
        "votes": restaurant.votes,
        "cost_for_two": restaurant.cost_for_two,
        "rest_types": restaurant.rest_types,
        "online_order": restaurant.online_order,
        "book_table": restaurant.book_table,
        "dishes_liked": dishes,
        "review_snippets": snippets,
    }


def build_user_prompt(
    preference: Preference,
    candidates: list[Restaurant],
    result_limit: int = 5,
) -> str:
    """
    Build the user-turn prompt containing preference context and candidate objects.

    Args:
        preference: The user's dining preferences.
        candidates: Pre-filtered, pre-ranked candidate list (at most CANDIDATE_LIMIT).
        result_limit: Maximum number of items to request in the response.

    Returns:
        A formatted string ready to send as the user message.
    """
    import json

    pref_block = {
        "location": preference.location,
        "budget": preference.budget,
        "cuisine": preference.cuisine,
        "min_rating": preference.min_rating,
        "extras": preference.extras,
    }
    # Remove None values to keep the prompt clean
    pref_block = {k: v for k, v in pref_block.items() if v is not None}

    candidate_objects = [_pack_candidate(r) for r in candidates]

    return (
        f"DINER PREFERENCES:\n{json.dumps(pref_block, ensure_ascii=False, indent=2)}\n\n"
        f"CANDIDATES ({len(candidates)} restaurants):\n"
        f"{json.dumps(candidate_objects, ensure_ascii=False, indent=2)}\n\n"
        f"Return the top {result_limit} restaurants ranked by suitability as JSON."
    )

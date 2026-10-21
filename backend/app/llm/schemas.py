"""
LLM Response Schemas (Phase 4).
Pydantic models for validating and parsing the structured JSON output
that the LLM is instructed to return.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRankedItem(BaseModel):
    """
    A single ranked restaurant item as returned by the LLM.
    Only id, rank, explanation, and vibe_tag are expected from the model —
    all catalog fields (rating, cost, name, etc.) are rehydrated from SQLite.
    """
    id: str = Field(description="Restaurant ID exactly as supplied in the prompt")
    rank: int = Field(description="1-based position in the ranked list")
    explanation: str = Field(
        description=(
            "Vivid 2-sentence rationale: sentence 1 mentions 1-2 signature dishes "
            "from dishes_liked; sentence 2 explains why it fits the diner's "
            "location, budget, and vibe."
        )
    )
    vibe_tag: str = Field(
        description=(
            "Concise AI-generated badge summarising the restaurant's vibe, "
            "e.g. 'Top-Rated Date Night', 'Authentic Biryani Spot', "
            "'Luxury Fine Dining', 'Casual Family Hangout'."
        )
    )


class LLMResponse(BaseModel):
    """
    Complete structured JSON output from the LLM.
    The model must return exactly this shape.
    """
    summary: str = Field(
        description="One short sentence summarising the recommendations for the diner"
    )
    recommendations: list[LLMRankedItem] = Field(
        description="Ranked list of restaurants; at most RESULT_LIMIT items"
    )

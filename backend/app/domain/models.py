"""
Domain models for DineMate.
Defines schemas for User Preferences, Restaurant Catalog entities,
and Recommendation outputs.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Preference(BaseModel):
    """
    User dining preferences collected via API or UI.
    """
    location: str | None = Field(default=None, description="Neighborhood or listing area in Bangalore")
    budget: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Budget band: low (<=400), medium (401-800), high (>=801)"
    )
    cuisine: str | None = Field(default=None, description="Desired cuisine, e.g. 'North Indian', 'Italian'")
    min_rating: float | None = Field(default=None, description="Minimum rating out of 5.0")
    extras: str | None = Field(
        default=None,
        description="Additional text or tags, e.g. 'family-friendly', 'quick bites', 'romantic'"
    )

    @field_validator("location", "cuisine", "extras", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator("budget", mode="before")
    @classmethod
    def validate_budget(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip().lower()
            if not val:
                return None
            if val in {"low", "medium", "high"}:
                return val
            raise ValueError(f"Invalid budget '{v}'. Allowed values are 'low', 'medium', 'high'.")
        return v

    @field_validator("min_rating")
    @classmethod
    def validate_min_rating(cls, v: float | None) -> float | None:
        if v is not None:
            if v < 0.0 or v > 5.0:
                raise ValueError("min_rating must be between 0.0 and 5.0.")
            return round(v, 1)
        return None


class Restaurant(BaseModel):
    """
    Canonical restaurant record persisted in SQLite/Parquet and used for filtering.
    """
    id: str = Field(description="Deterministic 16-char hex identifier")
    name: str = Field(description="Restaurant name")
    address: str = Field(default="", description="Street address")
    neighborhood: str = Field(default="", description="Neighborhood / location in Bangalore")
    listed_city: str = Field(default="", description="Broader listing area in Bangalore")
    cuisines: list[str] = Field(default_factory=list, description="Cuisines served")
    cuisines_raw: str = Field(default="", description="Raw comma-separated cuisine string")
    cost_for_two: int | None = Field(default=None, description="Approximate cost for two people in INR")
    rating: float | None = Field(default=None, description="Numeric rating out of 5.0")
    votes: int = Field(default=0, description="Total vote count on Zomato")
    rest_types: list[str] = Field(default_factory=list, description="Restaurant types, e.g. Quick Bites, Casual Dining")
    listed_types: list[str] = Field(default_factory=list, description="Listed meal types, e.g. Buffet, Delivery, Dine-out")
    online_order: bool = Field(default=False, description="Whether online ordering is available")
    book_table: bool = Field(default=False, description="Whether table booking is available")
    dishes_liked: list[str] = Field(default_factory=list, description="Popular / liked dishes")
    review_snippets: list[str] = Field(default_factory=list, description="Truncated customer reviews")
    url: str | None = Field(default=None, description="Zomato listing URL")


class RecommendationItem(BaseModel):
    """
    Single recommended venue card presented to the diner.
    """
    id: str
    rank: int = 1
    name: str
    cuisines: list[str] = Field(default_factory=list)
    rating: float | None = None
    votes: int = 0
    estimated_cost: int | None = None
    neighborhood: str = ""
    explanation: str = Field(description="Natural-language justification for why this fits")
    vibe_tag: str | None = Field(
        default=None,
        description="AI-generated concise vibe badge, e.g. 'Top-Rated Date Night'"
    )
    url: str | None = None


class RecommendationResponse(BaseModel):
    """
    Complete recommendation response payload for API and UI.
    """
    query: Preference
    candidate_count: int = 0
    relaxed_filters: list[str] = Field(default_factory=list)
    summary: str = ""
    source: Literal["llm", "heuristic"] = "heuristic"
    recommendations: list[RecommendationItem] = Field(default_factory=list)

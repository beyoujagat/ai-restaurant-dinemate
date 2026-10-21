"""
Budget Band Helpers (Phase 2).
Configurable budget band boundaries for DineMate:
  - Low:    <= 400 INR for two
  - Medium: 401 - 800 INR for two
  - High:   >= 801 INR for two
"""

from __future__ import annotations

import os


def get_budget_thresholds() -> tuple[int, int]:
    """
    Get configured thresholds (low_max, medium_max) from environment,
    defaulting to 400 and 800.
    """
    try:
        low_max = int(os.getenv("BUDGET_LOW_MAX", "400"))
    except (ValueError, TypeError):
        low_max = 400

    try:
        med_max = int(os.getenv("BUDGET_MEDIUM_MAX", "800"))
    except (ValueError, TypeError):
        med_max = 800

    return low_max, med_max


def get_budget_band(cost: int | None) -> str | None:
    """
    Determine the budget band for a given cost for two.
    Returns 'low', 'medium', 'high', or None if cost is missing.
    """
    if cost is None:
        return None

    low_max, med_max = get_budget_thresholds()

    if cost <= low_max:
        return "low"
    elif cost <= med_max:
        return "medium"
    else:
        return "high"


def is_in_budget(cost: int | None, band: str | None) -> bool:
    """
    Check whether a cost satisfies the target budget band.
    Missing cost fails budget matching if a specific band is requested.
    """
    if not band:
        return True
    if cost is None:
        return False
    return get_budget_band(cost) == band.strip().lower()


def get_budget_bounds(band: str) -> tuple[int | None, int | None]:
    """
    Return (min_inclusive, max_inclusive) for SQL queries or validation.
    """
    low_max, med_max = get_budget_thresholds()
    b = band.strip().lower()
    if b == "low":
        return None, low_max
    elif b == "medium":
        return low_max + 1, med_max
    elif b == "high":
        return med_max + 1, None
    raise ValueError(f"Unknown budget band: {band}")


def get_budget_label(band: str) -> str:
    """
    Human-readable label for UI options.
    """
    low_max, med_max = get_budget_thresholds()
    b = band.strip().lower()
    if b == "low":
        return f"≤ ₹{low_max} for two"
    elif b == "medium":
        return f"₹{low_max + 1}–₹{med_max} for two"
    elif b == "high":
        return f"≥ ₹{med_max + 1} for two"
    return band

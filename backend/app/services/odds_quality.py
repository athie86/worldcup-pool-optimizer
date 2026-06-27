"""
Bookmaker / market quality scoring  (spec WCPO-PRED-MODEL-V2 §8).

Computes the multiplicative weight applied to each bookmaker's de-vigged
target before consensus averaging:

    w = bookmaker_weight * freshness_weight * liquidity_weight
        * market_family_weight * outlier_weight

and enforces per-family total-weight caps so a large number of correlated
alternate lines cannot overwhelm the core 1X2 / totals signal.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np

# Default per-bookmaker weight; sharp books/exchanges can be boosted via config.
DEFAULT_BOOKMAKER_WEIGHT = 1.0
SHARP_BOOKMAKERS = {
    "pinnacle": 2.5,
    "betfair_ex_eu": 2.0,
    "betfair_ex_uk": 2.0,
    "matchbook": 1.75,
    "smarkets": 1.75,
}

FRESHNESS_HALF_LIFE_MINUTES = 180.0
FRESHNESS_MIN_WEIGHT = 0.10

MARKET_FAMILY_WEIGHT = {
    "result": 1.50,
    "total_goals": 1.25,
    "team_goals": 1.25,
    "both_teams_to_score": 1.00,
    "goal_difference": 0.75,
    "result_conditional_no_draw": 0.75,
    "first_half": 0.25,
    "fundamental_prior": 1.0,
}

# Cap on summed weight contributed by each family (spec §8.3).
MARKET_FAMILY_WEIGHT_CAPS = {
    "result": 3.0,
    "total_goals": 3.0,
    "team_goals": 3.0,
    "both_teams_to_score": 1.5,
    "goal_difference": 2.0,
    "result_conditional_no_draw": 1.0,
    "first_half": 0.5,
    "fundamental_prior": 3.0,
}


def bookmaker_weight(bookmaker_key: str) -> float:
    return SHARP_BOOKMAKERS.get((bookmaker_key or "").lower(), DEFAULT_BOOKMAKER_WEIGHT)


def freshness_weight(last_update: Optional[datetime],
                     now: Optional[datetime] = None,
                     half_life: float = FRESHNESS_HALF_LIFE_MINUTES) -> tuple[float, Optional[float]]:
    """Return (weight, age_minutes). Missing timestamp → neutral weight."""
    if last_update is None:
        return 1.0, None
    now = now or datetime.now(timezone.utc)
    try:
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        age_minutes = max(0.0, (now - last_update).total_seconds() / 60.0)
    except Exception:
        return 1.0, None
    w = math.exp(-age_minutes / half_life)
    return max(FRESHNESS_MIN_WEIGHT, w), age_minutes


def liquidity_weight(bet_limit: Optional[float], median_limit: Optional[float]) -> float:
    if not bet_limit or not median_limit or median_limit <= 0:
        return 1.0
    return float(np.clip(math.sqrt(bet_limit / median_limit), 0.5, 2.0))


def market_family_weight(family: str) -> float:
    return MARKET_FAMILY_WEIGHT.get(family, 1.0)


def outlier_weights(values: list[float]) -> list[float]:
    """Robust z-score downweighting against the median (spec §8.2)."""
    if len(values) < 3:
        return [1.0] * len(values)
    arr = np.array(values, dtype=float)
    med = np.median(arr)
    mad = np.median(np.abs(arr - med))
    if mad <= 1e-9:
        return [1.0] * len(values)
    z = 0.6745 * (arr - med) / mad
    out = []
    for zi in np.abs(z):
        if zi < 2.0:
            out.append(1.0)
        elif zi < 4.0:
            # linearly fade 0.75 → 0.25 across [2,4]
            out.append(float(0.75 - 0.25 * (zi - 2.0)))
        else:
            out.append(0.0)
    return out


def quality_label(bookmaker_count: int, freshness_minutes: Optional[float],
                  outlier_conflict: bool) -> str:
    fm = freshness_minutes if freshness_minutes is not None else 0.0
    if bookmaker_count >= 5 and fm <= 180 and not outlier_conflict:
        return "high"
    if bookmaker_count >= 2 and fm <= 360:
        return "medium"
    return "low"


def apply_family_cap(family: str, total_weight: float) -> float:
    cap = MARKET_FAMILY_WEIGHT_CAPS.get(family)
    if cap is None:
        return total_weight
    return min(total_weight, cap)

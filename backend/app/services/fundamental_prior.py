"""
Fundamental (non-market) team-strength prior  (spec WCPO-PRED-MODEL-V2 §5).

A log-linear expected-goals model used to anchor the score model when markets
are weak/missing, and to provide a reliability-weighted blend with the market
seed. Inputs are intentionally optional: with no team ratings it degrades to a
sensible, stage-aware neutral prior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import math

# Baseline league/tournament goal environment.
BASE_TOTAL_GOALS = 2.6
INTERCEPT = math.log(BASE_TOTAL_GOALS / 2.0)   # per-team baseline ≈ log(1.3)

HOME_ADVANTAGE = 0.25                            # log-goals bump for a true home side

# Stage adjustments to total goals (knockouts tend to be tighter).
STAGE_TOTAL_ADJUSTMENT = {
    "group": 0.0,
    "round_of_32": -0.05,
    "round_of_16": -0.07,
    "quarter_final": -0.10,
    "semi_final": -0.12,
    "final": -0.12,
}

# Convert an Elo difference into a log-goals attack/defence tilt.
ELO_TO_LOG_GOALS = 1.0 / 400.0 * math.log(10.0) * 0.5


@dataclass
class FundamentalInputs:
    home_team: str = ""
    away_team: str = ""
    neutral_venue: bool = True
    stage: str = "group"
    home_elo: Optional[float] = None
    away_elo: Optional[float] = None
    home_attack: Optional[float] = None      # log-goals offsets if provided directly
    away_attack: Optional[float] = None
    home_defense: Optional[float] = None
    away_defense: Optional[float] = None
    rest_adjustment: float = 0.0
    lineup_adjustment: float = 0.0


@dataclass
class FundamentalPrior:
    mu_home: float
    mu_away: float
    source: str
    diagnostics: dict = field(default_factory=dict)


def _stage_adjustment(stage: str) -> float:
    return STAGE_TOTAL_ADJUSTMENT.get((stage or "group").lower(), 0.0)


def build_fundamental_prior(inp: FundamentalInputs) -> FundamentalPrior:
    """Return expected goals (mu_home, mu_away) from the fundamental model."""
    stage_adj = _stage_adjustment(inp.stage)
    home_adv = 0.0 if inp.neutral_venue else HOME_ADVANTAGE

    # Attack/defence tilt: prefer explicit offsets, else derive from Elo.
    if inp.home_attack is not None and inp.away_attack is not None:
        atk_h, atk_a = inp.home_attack, inp.away_attack
        def_h = inp.home_defense or 0.0
        def_a = inp.away_defense or 0.0
        source = "explicit_offsets"
    elif inp.home_elo is not None and inp.away_elo is not None:
        diff = (inp.home_elo - inp.away_elo) * ELO_TO_LOG_GOALS
        atk_h, def_h = diff, diff
        atk_a, def_a = -diff, -diff
        source = "elo"
    else:
        atk_h = atk_a = def_h = def_a = 0.0
        source = "neutral_default"

    log_mu_home = (INTERCEPT + atk_h - def_a + home_adv + stage_adj
                   + inp.rest_adjustment + inp.lineup_adjustment)
    log_mu_away = (INTERCEPT + atk_a - def_h + stage_adj
                   + inp.rest_adjustment + inp.lineup_adjustment)

    mu_home = float(min(6.5, max(0.05, math.exp(log_mu_home))))
    mu_away = float(min(6.5, max(0.05, math.exp(log_mu_away))))

    return FundamentalPrior(
        mu_home=mu_home,
        mu_away=mu_away,
        source=source,
        diagnostics={
            "stage_adjustment": stage_adj,
            "home_advantage": home_adv,
            "log_mu_home": log_mu_home,
            "log_mu_away": log_mu_away,
        },
    )


def reliability_weight(
    bookmaker_count: int,
    n_market_families: int,
    freshness_minutes: Optional[float],
) -> float:
    """Compute the market-reliability weight w_market ∈ [0,1] (spec §5.4)."""
    if bookmaker_count <= 0 or n_market_families <= 0:
        return 0.0
    # bookmaker contribution saturates ~5 books
    book_term = min(1.0, bookmaker_count / 5.0)
    family_term = min(1.0, n_market_families / 3.0)
    if freshness_minutes is None:
        fresh_term = 0.8
    else:
        fresh_term = math.exp(-freshness_minutes / 360.0)
    w = 0.45 * book_term + 0.35 * family_term + 0.20 * fresh_term
    return float(min(0.98, max(0.0, w)))


def blend_mu(mu_market: float, mu_fundamental: float, w_market: float) -> float:
    return float(w_market * mu_market + (1.0 - w_market) * mu_fundamental)

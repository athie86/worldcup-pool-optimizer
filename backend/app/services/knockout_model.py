"""Knockout-stage probability extensions.

The core Dixon-Coles / entropy-calibrated model produces a 90-minute score
matrix.  For matches that can go to extra time and/or penalties this module
derives the supplementary probabilities needed to:

  1. Estimate the expected value of the KO progression bonuses
     (advance, penalty_winner).
  2. Recommend whether to pick home or away as the penalty-shootout winner.

The 90-minute model is unchanged; this runs as a post-processing step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.stats import poisson  # type: ignore[import]


@dataclass
class KnockoutExtras:
    """Supplementary probabilities for a knockout match."""

    p_draw_90: float
    """P(match is level after 90 minutes) — triggers extra time."""

    p_home_wins_et: float
    """P(home team scores more goals in ET | tied after 90)."""

    p_away_wins_et: float
    """P(away team scores more goals in ET | tied after 90)."""

    p_still_draw_after_et: float
    """P(still level after ET | tied after 90) — triggers penalties."""

    p_home_wins_penalties: float
    """P(home team wins shootout | goes to penalties)."""

    p_away_wins_penalties: float
    """P(away team wins shootout | goes to penalties)."""

    @property
    def optimal_penalties_winner(self) -> str:
        """The side more likely to win a shootout ('home' or 'away')."""
        return "home" if self.p_home_wins_penalties >= self.p_away_wins_penalties else "away"

    @property
    def p_goes_to_penalties(self) -> float:
        """P(match decided on penalties) — used in optimizer EP calculation."""
        return self.p_draw_90 * self.p_still_draw_after_et


# Extra-time lasts 30 minutes; goals arrive at roughly 1/3 the 90-min rate.
_ET_RATE_FACTOR = 1.0 / 3.0

# Penalty strength bias is clipped near 50/50: real-world data shows shootouts
# are close to a coin flip regardless of team quality.
_PEN_CLIP_LOW = 0.35
_PEN_CLIP_HIGH = 0.65

# ET goal grid size (0..N per team). 4 is generous — ET rarely exceeds 1 goal.
_ET_MAX = 4


def compute_knockout_extras(
    score_matrix: np.ndarray,
    lambda_home: float,
    lambda_away: float,
    scoring_basis: str,
) -> Optional[KnockoutExtras]:
    """Compute supplementary knockout probabilities from the 90-min model output.

    Returns None when ``scoring_basis`` is ``'ninety_minutes'`` (group stage or
    knockout stages where the pool scores 90-min result only).
    """
    if scoring_basis == "ninety_minutes":
        return None

    mat = np.asarray(score_matrix, dtype=float)
    p_draw_90 = float(np.trace(mat).sum()) if mat.ndim == 2 else 0.0

    # Default ET values (only overridden when extra_time is in scoring_basis)
    p_home_et = 0.0
    p_away_et = 0.0
    p_still_draw_et = 1.0  # if no ET model, assume penalties always follow draw

    if "extra_time" in scoring_basis:
        lh_et = float(lambda_home) * _ET_RATE_FACTOR
        la_et = float(lambda_away) * _ET_RATE_FACTOR

        et_range = range(_ET_MAX + 1)
        et_grid = np.outer(
            [poisson.pmf(g, lh_et) for g in et_range],
            [poisson.pmf(g, la_et) for g in et_range],
        )
        et_grid /= et_grid.sum()

        p_home_et = float(np.tril(et_grid, -1).sum())   # home_et > away_et
        p_away_et = float(np.triu(et_grid, 1).sum())    # away_et > home_et
        p_still_draw_et = float(np.trace(et_grid))       # level after ET

    # Penalties: slight strength bias derived from goal-rate ratio, clipped near 50/50.
    total_lam = float(lambda_home) + float(lambda_away)
    if total_lam > 0:
        raw_home_pen = float(lambda_home) / total_lam
    else:
        raw_home_pen = 0.5
    p_home_pen = float(np.clip(raw_home_pen, _PEN_CLIP_LOW, _PEN_CLIP_HIGH))

    return KnockoutExtras(
        p_draw_90=p_draw_90,
        p_home_wins_et=p_home_et,
        p_away_wins_et=p_away_et,
        p_still_draw_after_et=p_still_draw_et,
        p_home_wins_penalties=p_home_pen,
        p_away_wins_penalties=1.0 - p_home_pen,
    )

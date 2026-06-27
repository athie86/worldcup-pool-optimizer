from dataclasses import dataclass
from typing import Optional
import numpy as np
from .scoring import (
    ScoringRule, score_points, applies, result,
    COMBINE_BEST, COMBINE_ADDITIVE, KNOCKOUT_BONUS_CODES,
)
from .score_model import CalibratedModelResult, CANDIDATE_MAX
from .knockout_model import KnockoutExtras

# Backward-compat alias so any code that still references FitResult compiles.
FitResult = CalibratedModelResult


@dataclass
class Recommendation:
    predicted_home: int
    predicted_away: int
    rank: int
    expected_points: float
    variance: float
    zero_point_probability: float
    score_probability: float
    scoring_breakdown: dict
    penalties_winner: Optional[str] = None
    predicted_advancer: Optional[str] = None


def _advance_probabilities(
    mat: np.ndarray, extras: KnockoutExtras
) -> tuple[float, float]:
    """P(home advances), P(away advances) from the 90' matrix + KO extras.

    Advancing = win in 90, or (level after 90) win in ET, or (still level) win the
    shootout. The two probabilities sum to 1.
    """
    p_home_90 = float(np.tril(mat, -1).sum())   # home goals > away goals
    p_away_90 = float(np.triu(mat, 1).sum())    # away goals > home goals
    p_draw_90 = extras.p_draw_90

    p_home_adv = p_home_90 + p_draw_90 * (
        extras.p_home_wins_et
        + extras.p_still_draw_after_et * extras.p_home_wins_penalties
    )
    p_away_adv = p_away_90 + p_draw_90 * (
        extras.p_away_wins_et
        + extras.p_still_draw_after_et * extras.p_away_wins_penalties
    )
    return p_home_adv, p_away_adv


def compute_expected_points(
    fit: CalibratedModelResult,
    rules: list[ScoringRule],
    candidate_max: int = CANDIDATE_MAX,
    *,
    combine_mode: str = COMBINE_BEST,
    cap: Optional[float] = None,
    phase: str = "group",
    knockout_extras: Optional[KnockoutExtras] = None,
) -> list[Recommendation]:
    """Enumerate candidate predictions 0-0..candidate_max, compute expected points.

    Per-match score components are combined by ``combine_mode`` (``best`` = highest
    matching component wins, ``additive`` = sum) over the ``rules`` filtered by
    ``phase``, clamped to ``cap``.

    For knockout matches with ``knockout_extras``, the two progression bonuses
    (``advance`` for every prediction, ``penalty_winner`` for predicted draws) are
    added as expected value on top of the per-cell score. Because those bonuses
    depend on match-level ET/penalty probabilities rather than the 90' cell, they
    are computed outside the score-matrix loop. The per-phase cap is applied to the
    per-cell score; for the seeded additive pool the component values sum exactly
    to the cap, so this is exact in practice.
    """
    is_additive = combine_mode == COMBINE_ADDITIVE
    is_knockout = phase == "knockout" and knockout_extras is not None

    mat = fit.score_matrix
    fit_max = mat.shape[0] - 1

    # Enabled score components (excludes the KO progression bonuses).
    score_rules = [
        r for r in rules
        if r.enabled and r.phase == phase and r.code not in KNOCKOUT_BONUS_CODES
    ]

    # Knockout progression bonus rules (looked up once).
    advance_rule = next(
        (r for r in rules if r.code == "advance" and r.enabled and r.phase == phase), None
    )
    penalty_rule = next(
        (r for r in rules if r.code == "penalty_winner" and r.enabled and r.phase == phase), None
    )

    p_home_adv = p_away_adv = 0.0
    p_goes_to_penalties = 0.0
    optimal_pen_winner: Optional[str] = None
    if is_knockout:
        p_home_adv, p_away_adv = _advance_probabilities(mat, knockout_extras)
        p_goes_to_penalties = knockout_extras.p_goes_to_penalties
        optimal_pen_winner = knockout_extras.optimal_penalties_winner

    results = []

    for ph in range(candidate_max + 1):
        for pa in range(candidate_max + 1):
            ep = 0.0
            ep2 = 0.0
            p_zero = 0.0
            scoring_breakdown: dict[str, float] = {}

            for ah in range(fit_max + 1):
                for aa in range(fit_max + 1):
                    p_actual = float(mat[ah, aa])
                    if p_actual == 0.0:
                        continue
                    pts = score_points(
                        score_rules, ph, pa, ah, aa,
                        phase=phase, combine_mode=combine_mode, cap=cap,
                    )
                    ep += p_actual * pts
                    ep2 += p_actual * pts * pts
                    if pts == 0:
                        p_zero += p_actual

                    if pts > 0:
                        _attribute_breakdown(
                            scoring_breakdown, score_rules, ph, pa, ah, aa,
                            phase, is_additive, p_actual,
                        )

            # ── Knockout progression bonuses (expected value) ───────────────
            pen_winner_rec: Optional[str] = None
            if is_knockout:
                pred_is_draw = ph == pa
                predicted_advancer = (
                    optimal_pen_winner if pred_is_draw
                    else ("home" if ph > pa else "away")
                )
                if pred_is_draw:
                    pen_winner_rec = optimal_pen_winner

                # advance: points × P(the team this prediction sends through advances)
                if advance_rule is not None:
                    p_adv = p_home_adv if predicted_advancer == "home" else p_away_adv
                    contrib = advance_rule.points * p_adv
                    ep += contrib
                    ep2 += advance_rule.points ** 2 * p_adv
                    scoring_breakdown["advance"] = contrib

                # penalty_winner: draws only — points × P(goes to pens) × P(pick wins shootout)
                if penalty_rule is not None and pred_is_draw and optimal_pen_winner is not None:
                    p_correct_pen = (
                        knockout_extras.p_home_wins_penalties
                        if optimal_pen_winner == "home"
                        else knockout_extras.p_away_wins_penalties
                    )
                    contrib = penalty_rule.points * p_goes_to_penalties * p_correct_pen
                    ep += contrib
                    ep2 += penalty_rule.points ** 2 * p_goes_to_penalties * p_correct_pen
                    scoring_breakdown["penalty_winner"] = contrib

            variance = ep2 - ep * ep
            score_prob = float(mat[ph, pa]) if ph <= fit_max and pa <= fit_max else 0.0

            results.append(Recommendation(
                predicted_home=ph,
                predicted_away=pa,
                rank=0,
                expected_points=ep,
                variance=max(0.0, variance),
                zero_point_probability=p_zero,
                score_probability=score_prob,
                scoring_breakdown=scoring_breakdown,
                penalties_winner=pen_winner_rec,
            ))

    # Sort: EP desc, then zero_prob asc, variance asc, score_prob desc, total goals asc
    results.sort(key=lambda r: (
        -r.expected_points,
        r.zero_point_probability,
        r.variance,
        -r.score_probability,
        r.predicted_home + r.predicted_away,
    ))

    for i, r in enumerate(results):
        r.rank = i + 1

    return results


def _attribute_breakdown(
    breakdown: dict[str, float],
    score_rules: list[ScoringRule],
    ph: int, pa: int, ah: int, aa: int,
    phase: str, is_additive: bool, p_actual: float,
) -> None:
    """Attribute a positive per-cell score to its contributing component(s).

    Additive mode credits every matching component; best mode credits the single
    most-specific component that achieved the max, so the breakdown sums to EP.
    """
    matching = [
        r for r in score_rules
        if applies(r.code, ph, pa, ah, aa, config=r.config)
    ]
    if not matching:
        return
    if is_additive:
        for r in matching:
            if r.points > 0:
                breakdown[r.code] = breakdown.get(r.code, 0.0) + p_actual * r.points
    else:
        best_points = max(r.points for r in matching)
        if best_points <= 0:
            return
        best = min(
            (r for r in matching if r.points == best_points),
            key=lambda r: r.display_specificity_rank,
        )
        breakdown[best.code] = breakdown.get(best.code, 0.0) + p_actual * best.points

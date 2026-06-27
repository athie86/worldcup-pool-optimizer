"""Pool scoring engine.

A scoring system is a set of toggleable **components**, each a clear predicate
with a point value, combined per phase either by ``best`` (highest matching
component wins) or ``additive`` (every matching component sums), with an optional
per-match cap. Knockout adds two progression bonuses (``advance`` /
``penalty_winner``) that are summed on top of the phase score before the cap.

See ``app.core.defaults`` for the component catalog and the seeded presets.
"""
from dataclasses import dataclass
from typing import Optional


COMBINE_BEST = "best"
COMBINE_ADDITIVE = "additive"

# Components that are knockout-only progression bonuses (summed on top, never
# part of the best/additive combine over the per-match score components).
KNOCKOUT_BONUS_CODES = frozenset({"advance", "penalty_winner"})


@dataclass
class ScoringRule:
    code: str
    label: str
    points: float
    enabled: bool
    display_specificity_rank: int
    phase: str = "group"
    config: Optional[dict] = None


def result(home: int, away: int) -> str:
    if home > away:
        return "home_win"
    elif home == away:
        return "draw"
    else:
        return "away_win"


def goal_difference(home: int, away: int) -> int:
    return home - away


def winner_goals(home: int, away: int) -> Optional[int]:
    if home > away:
        return home
    elif away > home:
        return away
    return None


def _bucket(total: int, cap: Optional[int]) -> int:
    """Bucket a goal total: everything >= cap collapses into one bucket."""
    if cap is not None and total >= cap:
        return cap
    return total


def applies(
    rule_code: str,
    ph: int,
    pa: int,
    ah: int,
    aa: int,
    *,
    config: Optional[dict] = None,
    **kwargs,
) -> bool:
    """Check whether a scoring component applies for prediction (ph,pa) vs actual (ah,aa).

    Keyword args for knockout progression bonuses:
      went_to_penalties (bool): whether the match was decided in a shootout
      predicted_advancer (str|None): "home"/"away" — team the prediction sends through
      actual_advancer (str|None): "home"/"away" — team that actually advanced
      predicted_penalties_winner (str|None): "home"/"away" — draw prediction's pen pick
    """
    config = config or {}
    pred_result = result(ph, pa)
    actual_result = result(ah, aa)
    is_exact = (ph == ah and pa == aa)
    team_goal_match = (ph == ah or pa == aa)

    # ── Per-match score components ──────────────────────────────────────────
    if rule_code == "exact_score":
        return is_exact

    elif rule_code == "goal_difference":
        return (
            pred_result == actual_result
            and goal_difference(ph, pa) == goal_difference(ah, aa)
            and not is_exact
        )

    elif rule_code == "outcome_team_goals":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and team_goal_match
            and not is_exact
        )

    elif rule_code == "correct_outcome":
        return pred_result == actual_result

    elif rule_code == "team_goals":
        return team_goal_match

    elif rule_code == "total_goals":
        cap = config.get("bucket_cap")
        cap = int(cap) if cap is not None else None
        return _bucket(ph + pa, cap) == _bucket(ah + aa, cap)

    # ── Knockout progression bonuses ────────────────────────────────────────
    elif rule_code == "advance":
        # The team the prediction sends through actually advanced.
        pred_adv = kwargs.get("predicted_advancer")
        actual_adv = kwargs.get("actual_advancer")
        return pred_adv is not None and actual_adv is not None and pred_adv == actual_adv

    elif rule_code == "penalty_winner":
        # Only predicted draws can earn this: the penalty pick won the shootout.
        if pred_result != "draw":
            return False
        if not kwargs.get("went_to_penalties", False):
            return False
        ppw = kwargs.get("predicted_penalties_winner")
        actual_adv = kwargs.get("actual_advancer")
        return ppw is not None and actual_adv is not None and ppw == actual_adv

    return False


def score_points(
    rules: list[ScoringRule],
    ph: int,
    pa: int,
    ah: int,
    aa: int,
    *,
    phase: str = "group",
    combine_mode: str = COMBINE_BEST,
    cap: Optional[float] = None,
    **kwargs,
) -> float:
    """Score a prediction vs an actual result under a phase's combine settings.

    Per-match score components are combined by ``combine_mode`` (``best`` = max,
    ``additive`` = sum). Knockout progression bonuses (``advance`` /
    ``penalty_winner``) are always summed on top. The total is clamped to ``cap``.

    Knockout kwargs (``went_to_penalties``, ``predicted_advancer``,
    ``actual_advancer``, ``predicted_penalties_winner``) are forwarded to
    ``applies()``.
    """
    score_points_list: list[float] = []
    bonus_total = 0.0

    for rule in rules:
        if not rule.enabled or rule.phase != phase:
            continue
        if not applies(rule.code, ph, pa, ah, aa, config=rule.config, **kwargs):
            continue
        if rule.code in KNOCKOUT_BONUS_CODES:
            bonus_total += rule.points
        else:
            score_points_list.append(rule.points)

    if combine_mode == COMBINE_ADDITIVE:
        base = sum(score_points_list)
    else:
        base = max(score_points_list) if score_points_list else 0.0

    total = base + bonus_total
    if cap is not None:
        total = min(total, cap)
    return total


def get_display_label(
    rules: list[ScoringRule],
    ph: int,
    pa: int,
    ah: int,
    aa: int,
    *,
    phase: str = "group",
) -> str:
    """Return the display label of the most specific applicable score component."""
    applicable = [
        rule for rule in rules
        if rule.enabled
        and rule.phase == phase
        and rule.code not in KNOCKOUT_BONUS_CODES
        and applies(rule.code, ph, pa, ah, aa, config=rule.config)
    ]
    if not applicable:
        return "No points"
    best_points = max(r.points for r in applicable)
    best_rules = [r for r in applicable if r.points == best_points]
    # Pick by highest specificity (lower rank = more specific)
    return min(best_rules, key=lambda r: r.display_specificity_rank).label

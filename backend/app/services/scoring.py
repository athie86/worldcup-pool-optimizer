from dataclasses import dataclass
from typing import Optional


@dataclass
class ScoringRule:
    code: str
    label: str
    points: float
    enabled: bool
    display_specificity_rank: int


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


def applies(rule_code: str, ph: int, pa: int, ah: int, aa: int) -> bool:
    """Check if a scoring rule applies given prediction (ph,pa) and actual (ah,aa)."""
    pred_result = result(ph, pa)
    actual_result = result(ah, aa)
    is_exact = (ph == ah and pa == aa)

    if rule_code == "exact_score":
        return is_exact

    elif rule_code == "correct_winner_goal_difference":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and goal_difference(ph, pa) == goal_difference(ah, aa)
            and not is_exact
        )

    elif rule_code == "correct_winner_winner_goals":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and winner_goals(ph, pa) == winner_goals(ah, aa)
            and not is_exact
        )

    elif rule_code == "correct_winner_any_team_goals":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and (ph == ah or pa == aa)
            and not is_exact
        )

    elif rule_code == "correct_winner_basic_a":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and not is_exact
            and goal_difference(ph, pa) != goal_difference(ah, aa)
        )

    elif rule_code == "correct_winner_basic_b":
        return (
            pred_result == actual_result
            and pred_result != "draw"
            and not is_exact
            and winner_goals(ph, pa) != winner_goals(ah, aa)
        )

    elif rule_code == "correct_draw":
        return (
            pred_result == "draw"
            and actual_result == "draw"
            and not is_exact
        )

    elif rule_code == "wrong_result_team_goal":
        return (
            pred_result != actual_result
            and (ph == ah or pa == aa)
        )

    elif rule_code == "wrong_result":
        return True  # catch-all, always applies

    return False


def score_points(rules: list[ScoringRule], ph: int, pa: int, ah: int, aa: int) -> float:
    """Return highest applicable enabled rule points for prediction vs actual."""
    applicable = [
        rule.points
        for rule in rules
        if rule.enabled and applies(rule.code, ph, pa, ah, aa)
    ]
    return max(applicable) if applicable else 0.0


def binary_score_points(
    ph: int,
    pa: int,
    ah: int,
    aa: int,
    result_points: float = 1.0,
    total_goals_points: float = 1.0,
) -> float:
    """Binary scoring: points for a correct result and/or correct total goals.

    Awards ``result_points`` when the predicted result (home win / draw /
    away win) matches the actual result, and ``total_goals_points`` when the
    predicted total goals (home + away) match the actual total. The two
    components are independent, so a prediction can earn 0, one, or both.
    """
    pts = 0.0
    if result(ph, pa) == result(ah, aa):
        pts += result_points
    if (ph + pa) == (ah + aa):
        pts += total_goals_points
    return pts


def get_display_label(rules: list[ScoringRule], ph: int, pa: int, ah: int, aa: int) -> str:
    """Return the display label of the most specific applicable rule."""
    applicable = [
        rule for rule in rules
        if rule.enabled and applies(rule.code, ph, pa, ah, aa)
    ]
    if not applicable:
        return "No points"
    best_points = max(r.points for r in applicable)
    best_rules = [r for r in applicable if r.points == best_points]
    # Pick by highest specificity (lower rank = more specific)
    return min(best_rules, key=lambda r: r.display_specificity_rank).label

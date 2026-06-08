"""Shared default values used by both the seed script and the API.

Keeping the default scoring rules in one place means the seed script, the
"create pool configuration" endpoint, and the "reset to defaults" endpoint all
stay in sync.
"""
from __future__ import annotations


# The canonical default pool scoring system. `display_specificity_rank` orders
# the rules from most specific (exact score) to least specific (catch-all) which
# is also the order the scoring engine evaluates them in.
DEFAULT_SCORING_RULES: list[dict] = [
    {
        "code": "exact_score",
        "label": "Exact Score",
        "description": "Predict the exact final score (90 min)",
        "points": 10.0,
        "enabled": True,
        "display_specificity_rank": 1,
    },
    {
        "code": "correct_winner_goal_difference",
        "label": "Correct Winner + Goal Difference",
        "description": "Correct winner and correct goal difference (not exact score)",
        "points": 6.0,
        "enabled": True,
        "display_specificity_rank": 2,
    },
    {
        "code": "correct_winner_winner_goals",
        "label": "Correct Winner + Winner's Goals",
        "description": "Correct winner and correct goals for winning team (not exact score)",
        "points": 5.0,
        "enabled": True,
        "display_specificity_rank": 3,
    },
    {
        "code": "correct_winner_any_team_goals",
        "label": "Correct Winner + Any Team's Goals",
        "description": "Correct winner and correct goals for any team, winner or loser (not exact score)",
        "points": 4.0,
        "enabled": True,
        "display_specificity_rank": 4,
    },
    {
        "code": "correct_winner_basic_a",
        "label": "Correct Winner (A)",
        "description": "Correct winner, wrong goal difference",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 5,
    },
    {
        "code": "correct_winner_basic_b",
        "label": "Correct Winner (B)",
        "description": "Correct winner, wrong goals for winner",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 6,
    },
    {
        "code": "correct_draw",
        "label": "Correct Draw",
        "description": "Predicted draw and it was a draw (not exact score)",
        "points": 4.0,
        "enabled": True,
        "display_specificity_rank": 7,
    },
    {
        "code": "wrong_result_team_goal",
        "label": "Wrong Result, One Team's Goals Correct",
        "description": "Wrong result but one team's goal count matches",
        "points": 1.0,
        "enabled": True,
        "display_specificity_rank": 8,
    },
    {
        "code": "wrong_result",
        "label": "Wrong Result",
        "description": "Catch-all: wrong result, no partial credit",
        "points": 0.0,
        "enabled": True,
        "display_specificity_rank": 9,
    },
]

"""Shared default values used by both the seed script and the API.

Keeping the default scoring rules in one place means the seed script, the
"create pool configuration" endpoint, and the "reset to defaults" endpoint all
stay in sync.
"""
from __future__ import annotations


_BASE_RULES: list[dict] = [
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
        "code": "correct_winner_only",
        "label": "Correct Winner Only",
        "description": "Correct winner but wrong goals for both teams (no exact score, neither team's goals match)",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 5,
    },
    {
        "code": "correct_winner_basic_a",
        "label": "Correct Winner (A)",
        "description": "Correct winner, wrong goal difference",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 6,
    },
    {
        "code": "correct_winner_basic_b",
        "label": "Correct Winner (B)",
        "description": "Correct winner, wrong goals for winner",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 7,
    },
    {
        "code": "correct_draw",
        "label": "Correct Draw",
        "description": "Predicted draw and it was a draw (not exact score)",
        "points": 4.0,
        "enabled": True,
        "display_specificity_rank": 8,
    },
    {
        "code": "wrong_result_team_goal",
        "label": "Wrong Result, One Team's Goals Correct",
        "description": "Wrong result but one team's goal count matches",
        "points": 1.0,
        "enabled": True,
        "display_specificity_rank": 9,
    },
    {
        "code": "wrong_result",
        "label": "Wrong Result",
        "description": "Catch-all: wrong result, no partial credit",
        "points": 0.0,
        "enabled": True,
        "display_specificity_rank": 10,
    },
]

_KNOCKOUT_EXTRA_RULES: list[dict] = [
    {
        "code": "knockout_tie_to_penalties",
        "label": "KO: Correct Tie (Goes to Penalties)",
        "description": "Predicted draw AND match went to a penalty shootout",
        "points": 4.0,
        "enabled": True,
        "display_specificity_rank": 11,
        "phase": "knockout",
    },
    {
        "code": "knockout_penalties_winner",
        "label": "KO: Correct Penalty Winner",
        "description": "Predicted the team that wins the penalty shootout",
        "points": 3.0,
        "enabled": True,
        "display_specificity_rank": 12,
        "phase": "knockout",
    },
]


def get_default_rules() -> list[dict]:
    """Return the full default rule set: 10 group rules + 10 knockout rules + 2 KO-only rules."""
    group_rules = [{**r, "phase": "group"} for r in _BASE_RULES]
    knockout_rules = [{**r, "phase": "knockout"} for r in _BASE_RULES]
    return group_rules + knockout_rules + _KNOCKOUT_EXTRA_RULES


# Backward-compat alias: existing callers that reference DEFAULT_SCORING_RULES
# now get the full 22-rule list. The phase field is new but ignored by any
# code that doesn't know about it.
DEFAULT_SCORING_RULES: list[dict] = get_default_rules()

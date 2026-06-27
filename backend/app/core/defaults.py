"""Shared scoring defaults: the component catalog and the seed presets.

This is the single source of truth for the scoring system, consumed by the seed
script, the "create pool configuration" / "reset to defaults" endpoints, and the
0008 migration. A *scoring system* (preset) is one ``PoolConfig`` plus a set of
``ScoringRule`` rows.

The model is deliberately simple and uniform:

* A small **catalog of components** (below), each a clear predicate with a
  worked example. Every component exists for both the ``group`` and ``knockout``
  phases.
* Each phase picks a **combine mode** — ``best`` (award the single highest
  matching component) or ``additive`` (sum every matching component) — with an
  optional per-match **cap**.
* Knockout adds two **progression bonuses** (``advance`` / ``penalty_winner``)
  that are always summed on top of the phase score, before the cap.

The four presets at the bottom reproduce four real-world World Cup pools.
"""
from __future__ import annotations

from copy import deepcopy


# ── Combine modes ───────────────────────────────────────────────────────────
COMBINE_BEST = "best"          # highest-value matching component wins (a ladder)
COMBINE_ADDITIVE = "additive"  # every matching component sums

# ── Knockout scoring bases (subset of core.knockout_config vocabulary) ──────
BASIS_90 = "ninety_minutes"
BASIS_ET = "ninety_minutes_extra_time"
BASIS_ET_PENS = "ninety_minutes_extra_time_penalties"


# ── Component catalog ───────────────────────────────────────────────────────
# One dict per component. ``points``/``enabled``/``config`` here are catalog
# *defaults*; each preset overrides them. ``display_specificity_rank`` orders
# the components most-specific → least-specific for display and labelling.
#
# Per-match score components (apply to both phases):
_SCORE_COMPONENTS: list[dict] = [
    {
        "code": "exact_score",
        "label": "Exact score",
        "description": "Your predicted final score matches exactly (this also covers exact draws).",
        "example": "You predict 2-1 and it ends 2-1.",
        "display_specificity_rank": 1,
    },
    {
        "code": "goal_difference",
        "label": "Correct result + goal difference",
        "description": "You get the result right (win/draw/loss) and the exact goal difference, but not the exact score. A predicted draw counts here too (difference of 0).",
        "example": "You predict 3-1 (a 2-goal win) and it ends 2-0; or you predict a draw and it's a draw.",
        "display_specificity_rank": 2,
    },
    {
        "code": "outcome_team_goals",
        "label": "Correct result + a team's goals",
        "description": "You get the winner right and at least one team's exact goal count, but not the full exact score.",
        "example": "You predict 2-0 and it ends 2-1 (winner right, home team's 2 goals right).",
        "display_specificity_rank": 3,
        "config": {"which": "any"},
    },
    {
        "code": "correct_outcome",
        "label": "Correct result (1/X/2)",
        "description": "You pick the right outcome — home win, draw or away win — regardless of the score.",
        "example": "You predict 1-0 and it ends 3-1 (you said home win, home won).",
        "display_specificity_rank": 4,
    },
    {
        "code": "team_goals",
        "label": "A team's goals",
        "description": "At least one team's exact goal count matches, even if you got the winner wrong.",
        "example": "You predict 2-1 and it ends 0-1 (the away team's 1 goal is right).",
        "display_specificity_rank": 5,
        "config": {"which": "any"},
    },
    {
        "code": "total_goals",
        "label": "Correct total goals",
        "description": "The total number of goals (home + away) matches. With a bucket cap, totals at or above the cap share one bucket (e.g. cap 4 means 4+).",
        "example": "You predict a total of 3 goals (e.g. 2-1) and it ends with 3 goals (e.g. 0-3).",
        "display_specificity_rank": 6,
    },
]

# Knockout-only progression bonuses (always summed on top, before the cap):
_KNOCKOUT_BONUSES: list[dict] = [
    {
        "code": "advance",
        "label": "Correct team advances",
        "description": "The team your prediction sends through actually advances — your predicted winner, or (if you predicted a draw) your penalty-shootout pick. Applies to every prediction.",
        "example": "You predict Brazil to win (or pick Brazil on penalties) and Brazil advances.",
        "display_specificity_rank": 7,
    },
    {
        "code": "penalty_winner",
        "label": "Correct penalty-shootout winner",
        "description": "You predicted a draw and your penalty-shootout pick wins the shootout. If you predicted a win but the match went to penalties, you earn nothing here.",
        "example": "You predict 1-1 with Spain advancing on penalties, it ends 1-1 and Spain win the shootout.",
        "display_specificity_rank": 8,
    },
]


def _catalog(phase: str) -> list[dict]:
    """All catalog components for a phase, with defaults (disabled, 0 points)."""
    rows = deepcopy(_SCORE_COMPONENTS)
    if phase == "knockout":
        rows += deepcopy(_KNOCKOUT_BONUSES)
    out = []
    for r in rows:
        r.setdefault("config", None)
        out.append({
            **r,
            "points": 0.0,
            "enabled": False,
            "phase": phase,
        })
    return out


def get_catalog_codes(phase: str) -> list[str]:
    """Component codes valid for a phase (score components, plus KO bonuses)."""
    return [r["code"] for r in _catalog(phase)]


# ── Preset definitions ──────────────────────────────────────────────────────
# Each preset lists, per phase, the components it *enables* with their points
# (and optional config). Everything else in the catalog is seeded disabled.

# code -> {points, config?}
def _on(points: float, config: dict | None = None) -> dict:
    d: dict = {"points": float(points)}
    if config is not None:
        d["config"] = config
    return d


SEED_PRESETS: list[dict] = [
    {
        "name": "Trivia Mundialista",
        "description": "Additive pool: correct result + correct total goals. Knockouts reward who advances, the exact score and total goals (capped).",
        "group_combine_mode": COMBINE_ADDITIVE,
        "knockout_combine_mode": COMBINE_ADDITIVE,
        "group_cap": None,
        "knockout_cap": 6.0,
        "knockout_scoring_basis": BASIS_ET_PENS,
        "pick_lock_minutes_before": 60,
        "group": {
            "correct_outcome": _on(3),
            "total_goals": _on(1, {"bucket_cap": 4}),
        },
        "knockout": {
            "advance": _on(3),
            "exact_score": _on(2),
            "total_goals": _on(1),
        },
    },
    {
        "name": "Scores & Rules App",
        "description": "Tiered 90-minute pool: exact score, goal difference (or draw), or correct winner.",
        "group_combine_mode": COMBINE_BEST,
        "knockout_combine_mode": COMBINE_BEST,
        "group_cap": None,
        "knockout_cap": None,
        "knockout_scoring_basis": BASIS_90,
        "pick_lock_minutes_before": 1,
        "group": {
            "exact_score": _on(5),
            "goal_difference": _on(3),
            "correct_outcome": _on(2),
        },
        "knockout": {
            "exact_score": _on(5),
            "goal_difference": _on(3),
            "correct_outcome": _on(2),
        },
    },
    {
        "name": "Qini 2026",
        "description": "Simple tiered pool: exact score, otherwise the correct result. Scored at 90 minutes plus stoppage time.",
        "group_combine_mode": COMBINE_BEST,
        "knockout_combine_mode": COMBINE_BEST,
        "group_cap": None,
        "knockout_cap": None,
        "knockout_scoring_basis": BASIS_90,
        "pick_lock_minutes_before": None,
        "group": {
            "exact_score": _on(3),
            "correct_outcome": _on(1),
        },
        "knockout": {
            "exact_score": _on(3),
            "correct_outcome": _on(1),
        },
    },
    {
        "name": "World Cup 2026",
        "description": "Detailed tiered pool: exact score, correct winner + a team's goals, correct winner, or a team's goals. Knockouts add a penalty-shootout bonus for predicted draws.",
        "group_combine_mode": COMBINE_BEST,
        "knockout_combine_mode": COMBINE_BEST,
        "group_cap": None,
        "knockout_cap": None,
        "knockout_scoring_basis": BASIS_ET_PENS,
        "pick_lock_minutes_before": 1,
        "group": {
            "exact_score": _on(6),
            "outcome_team_goals": _on(4),
            "correct_outcome": _on(3),
            "team_goals": _on(1),
        },
        "knockout": {
            "exact_score": _on(6),
            "outcome_team_goals": _on(4),
            "correct_outcome": _on(3),
            "team_goals": _on(1),
            "penalty_winner": _on(3),
        },
    },
]


def build_preset_rules(preset: dict) -> list[dict]:
    """Return the full scoring-rule rows for a preset (whole catalog, both phases).

    Components the preset enables get its points/config and ``enabled=True``;
    every other catalog component is included disabled with 0 points, so the UI
    can show — and the user can turn on — the complete set.
    """
    rules: list[dict] = []
    for phase in ("group", "knockout"):
        enabled_map = preset.get(phase, {})
        for row in _catalog(phase):
            override = enabled_map.get(row["code"])
            if override is not None:
                row["enabled"] = True
                row["points"] = float(override["points"])
                if "config" in override:
                    row["config"] = override["config"]
            rules.append(row)
    return rules


def get_default_rules() -> list[dict]:
    """Default rules for a brand-new, hand-created config.

    Used when a user creates an empty config (not one of the named presets):
    seed the full catalog for both phases, with the "World Cup 2026" preset's
    values as a sensible starting ladder.
    """
    default_preset = next(p for p in SEED_PRESETS if p["name"] == "World Cup 2026")
    return build_preset_rules(default_preset)


# Backward-compat alias (the seed script imports this name).
DEFAULT_SCORING_RULES: list[dict] = get_default_rules()

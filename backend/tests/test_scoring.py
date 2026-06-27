"""Tests for the unified scoring engine and the four seeded presets."""
import pytest

from app.services.scoring import (
    ScoringRule,
    applies,
    score_points,
    get_display_label,
    result,
    goal_difference,
    winner_goals,
    COMBINE_BEST,
    COMBINE_ADDITIVE,
)
from app.core.defaults import SEED_PRESETS, build_preset_rules


# ── Helpers ─────────────────────────────────────────────────────────────────
def _preset(name: str) -> dict:
    return next(p for p in SEED_PRESETS if p["name"] == name)


def _rules_for(name: str, phase: str) -> list[ScoringRule]:
    preset = _preset(name)
    return [
        ScoringRule(
            code=r["code"],
            label=r["label"],
            points=r["points"],
            enabled=r["enabled"],
            display_specificity_rank=r["display_specificity_rank"],
            phase=r["phase"],
            config=r.get("config"),
        )
        for r in build_preset_rules(preset)
        if r["phase"] == phase
    ]


def _score(name: str, phase: str, ph, pa, ah, aa, **kwargs) -> float:
    preset = _preset(name)
    return score_points(
        _rules_for(name, phase), ph, pa, ah, aa,
        phase=phase,
        combine_mode=preset[f"{phase}_combine_mode"],
        cap=preset[f"{phase}_cap"],
        **kwargs,
    )


# ── Basic helpers ───────────────────────────────────────────────────────────
class TestBasicFunctions:
    def test_result(self):
        assert result(2, 1) == "home_win"
        assert result(1, 1) == "draw"
        assert result(0, 1) == "away_win"

    def test_goal_difference(self):
        assert goal_difference(3, 1) == 2
        assert goal_difference(1, 3) == -2

    def test_winner_goals(self):
        assert winner_goals(3, 1) == 3
        assert winner_goals(0, 2) == 2
        assert winner_goals(1, 1) is None


# ── Component predicates ────────────────────────────────────────────────────
class TestApplies:
    def test_exact_score(self):
        assert applies("exact_score", 2, 1, 2, 1) is True
        assert applies("exact_score", 2, 1, 2, 0) is False

    def test_goal_difference_decisive(self):
        assert applies("goal_difference", 3, 1, 2, 0) is True   # GD 2 == 2, not exact
        assert applies("goal_difference", 2, 1, 2, 1) is False  # exact excluded

    def test_goal_difference_counts_draws(self):
        # A predicted draw vs an actual draw shares GD 0 — "goal difference or draw".
        assert applies("goal_difference", 1, 1, 0, 0) is True
        assert applies("goal_difference", 1, 1, 1, 1) is False  # exact excluded

    def test_outcome_team_goals(self):
        assert applies("outcome_team_goals", 2, 0, 2, 1) is True   # winner + home goals
        assert applies("outcome_team_goals", 2, 0, 3, 1) is False  # no team-goal match
        assert applies("outcome_team_goals", 2, 1, 0, 1, ) is False  # wrong winner
        assert applies("outcome_team_goals", 1, 1, 1, 1) is False  # draw excluded

    def test_correct_outcome(self):
        assert applies("correct_outcome", 1, 0, 3, 1) is True
        assert applies("correct_outcome", 1, 1, 2, 2) is True
        assert applies("correct_outcome", 1, 0, 0, 1) is False

    def test_team_goals(self):
        assert applies("team_goals", 2, 1, 0, 1) is True   # away 1 matches
        assert applies("team_goals", 2, 1, 0, 3) is False

    def test_total_goals_exact(self):
        assert applies("total_goals", 2, 1, 0, 3) is True   # total 3 == 3
        assert applies("total_goals", 2, 1, 0, 2) is False

    def test_total_goals_bucketed(self):
        cfg = {"bucket_cap": 4}
        # 4 and 6 both land in the "4+" bucket.
        assert applies("total_goals", 2, 2, 5, 1, config=cfg) is True
        # 3 is its own bucket, distinct from 4+.
        assert applies("total_goals", 2, 1, 2, 2, config=cfg) is False

    def test_advance(self):
        assert applies("advance", 1, 1, 1, 1,
                       predicted_advancer="home", actual_advancer="home") is True
        assert applies("advance", 1, 1, 1, 1,
                       predicted_advancer="home", actual_advancer="away") is False

    def test_penalty_winner_only_for_predicted_draw(self):
        # Predicted draw, went to pens, pick advanced → applies.
        assert applies("penalty_winner", 1, 1, 1, 1, went_to_penalties=True,
                       predicted_penalties_winner="home", actual_advancer="home") is True
        # Predicted a win → never applies, even if it went to pens.
        assert applies("penalty_winner", 2, 1, 1, 1, went_to_penalties=True,
                       predicted_penalties_winner="home", actual_advancer="home") is False
        # Did not go to penalties → no bonus.
        assert applies("penalty_winner", 1, 1, 1, 1, went_to_penalties=False,
                       predicted_penalties_winner="home", actual_advancer="home") is False


# ── Combine modes + cap ─────────────────────────────────────────────────────
class TestCombineModes:
    def _ladder(self):
        return [
            ScoringRule("exact_score", "Exact", 6, True, 1),
            ScoringRule("correct_outcome", "Result", 3, True, 4),
            ScoringRule("total_goals", "Total", 1, True, 6),
        ]

    def test_best_takes_max(self):
        # Exact also matches result+total, but best awards only the highest (6).
        assert score_points(self._ladder(), 2, 1, 2, 1, combine_mode=COMBINE_BEST) == 6

    def test_additive_sums(self):
        # 2-1 vs 2-1: exact(6) + result(3) + total(1) = 10.
        assert score_points(self._ladder(), 2, 1, 2, 1, combine_mode=COMBINE_ADDITIVE) == 10

    def test_cap_clamps(self):
        assert score_points(self._ladder(), 2, 1, 2, 1,
                            combine_mode=COMBINE_ADDITIVE, cap=7) == 7

    def test_disabled_rule_ignored(self):
        rules = [ScoringRule("exact_score", "Exact", 6, False, 1)]
        assert score_points(rules, 1, 0, 1, 0, combine_mode=COMBINE_BEST) == 0


# ── Four-pool reproduction (from the seeded presets) ────────────────────────
class TestTriviaMundialista:
    NAME = "Trivia Mundialista"

    def test_group_outcome_plus_total(self):
        # 2-1 vs 2-1: correct outcome (3) + total 3==3 (1) = 4.
        assert _score(self.NAME, "group", 2, 1, 2, 1) == 4

    def test_group_outcome_only(self):
        # 2-1 vs 1-0: home win right (3), total 3 vs 1 wrong → 3.
        assert _score(self.NAME, "group", 2, 1, 1, 0) == 3

    def test_group_total_bucketed(self):
        # 2-2 (total 4) vs 5-1 (total 6): same 4+ bucket (1); outcome draw vs home win → 1.
        assert _score(self.NAME, "group", 2, 2, 5, 1) == 1

    def test_knockout_capped_at_six(self):
        # 3-0 vs 3-0, home advances: exact(2)+total(1)+advance(3)=6 (== cap).
        pts = _score(self.NAME, "knockout", 3, 0, 3, 0,
                     predicted_advancer="home", actual_advancer="home")
        assert pts == 6

    def test_knockout_partial(self):
        # 1-0 vs 2-0, home advances: exact no, total 1 vs 2 no, advance(3) = 3.
        pts = _score(self.NAME, "knockout", 1, 0, 2, 0,
                     predicted_advancer="home", actual_advancer="home")
        assert pts == 3


class TestScoresRulesApp:
    NAME = "Scores & Rules App"

    def test_exact(self):
        assert _score(self.NAME, "group", 2, 0, 2, 0) == 5

    def test_goal_difference_tier(self):
        assert _score(self.NAME, "group", 3, 1, 2, 0) == 3  # GD 2, not exact

    def test_draw_counts_as_goal_difference(self):
        assert _score(self.NAME, "group", 1, 1, 0, 0) == 3

    def test_winner_tier(self):
        assert _score(self.NAME, "group", 1, 0, 3, 1) == 2

    def test_miss(self):
        assert _score(self.NAME, "group", 1, 2, 2, 0) == 0


class TestQini2026:
    NAME = "Qini 2026"

    def test_exact_does_not_stack(self):
        # Best mode: exact (3) does not also add the result point.
        assert _score(self.NAME, "group", 2, 1, 2, 1) == 3

    def test_result_only(self):
        assert _score(self.NAME, "group", 2, 1, 1, 0) == 1

    def test_draw_result(self):
        assert _score(self.NAME, "group", 1, 1, 0, 0) == 1


class TestWorldCup2026:
    NAME = "World Cup 2026"

    def test_exact(self):
        assert _score(self.NAME, "group", 2, 1, 2, 1) == 6

    def test_outcome_plus_team_goals(self):
        assert _score(self.NAME, "group", 2, 0, 2, 1) == 4

    def test_correct_outcome(self):
        assert _score(self.NAME, "group", 1, 0, 3, 1) == 3

    def test_team_goals_wrong_winner(self):
        assert _score(self.NAME, "group", 2, 1, 0, 1) == 1

    def test_exact_draw(self):
        assert _score(self.NAME, "group", 1, 1, 1, 1) == 6

    def test_draw_no_exact(self):
        assert _score(self.NAME, "group", 0, 0, 2, 2) == 3

    # Knockout penalty bonuses reproduce the 9/6/6/3 table.
    def _ko(self, ph, pa, ah, aa, **kw):
        return _score(self.NAME, "knockout", ph, pa, ah, aa, **kw)

    def test_exact_draw_correct_pen(self):
        assert self._ko(1, 1, 1, 1, went_to_penalties=True,
                        predicted_penalties_winner="home", actual_advancer="home") == 9

    def test_exact_draw_wrong_pen(self):
        assert self._ko(1, 1, 1, 1, went_to_penalties=True,
                        predicted_penalties_winner="home", actual_advancer="away") == 6

    def test_draw_no_exact_correct_pen(self):
        assert self._ko(0, 0, 2, 2, went_to_penalties=True,
                        predicted_penalties_winner="home", actual_advancer="home") == 6

    def test_draw_no_exact_wrong_pen(self):
        assert self._ko(0, 0, 2, 2, went_to_penalties=True,
                        predicted_penalties_winner="home", actual_advancer="away") == 3

    def test_predicted_win_into_draw_earns_no_pen(self):
        # Predicted 2-1 (a win), match ends 1-1 and goes to pens: no penalty bonus,
        # only the away team's 1 goal matches → 1.
        assert self._ko(2, 1, 1, 1, went_to_penalties=True,
                        predicted_penalties_winner="home", actual_advancer="home") == 1


# ── Display label ───────────────────────────────────────────────────────────
class TestDisplayLabel:
    def test_exact_label(self):
        rules = _rules_for("World Cup 2026", "group")
        assert get_display_label(rules, 2, 1, 2, 1, phase="group") == "Exact score"

    def test_no_points_label(self):
        rules = [ScoringRule("exact_score", "Exact", 6, False, 1)]
        assert get_display_label(rules, 1, 0, 1, 0) == "No points"


# ── Catalog integrity (guards the tooltip requirement) ──────────────────────
class TestCatalogIntegrity:
    def test_four_presets_exist(self):
        names = {p["name"] for p in SEED_PRESETS}
        assert names == {
            "Trivia Mundialista", "Scores & Rules App", "Qini 2026", "World Cup 2026",
        }

    def test_every_rule_has_an_example(self):
        for preset in SEED_PRESETS:
            for rule in build_preset_rules(preset):
                assert rule.get("example"), f"{preset['name']}/{rule['code']} missing example"

    def test_combine_modes_and_caps(self):
        a = _preset("Trivia Mundialista")
        assert a["group_combine_mode"] == COMBINE_ADDITIVE
        assert a["knockout_combine_mode"] == COMBINE_ADDITIVE
        assert a["knockout_cap"] == 6.0
        d = _preset("World Cup 2026")
        assert d["group_combine_mode"] == COMBINE_BEST
        assert d["knockout_scoring_basis"] == "ninety_minutes_extra_time_penalties"

"""Tests for the scoring engine."""
import pytest
from app.services.scoring import (
    ScoringRule,
    applies,
    score_points,
    binary_score_points,
    get_display_label,
    result,
    goal_difference,
    winner_goals,
)


@pytest.fixture
def rules() -> list[ScoringRule]:
    return [
        ScoringRule(code="exact_score", label="Exact Score", points=10.0, enabled=True, display_specificity_rank=1),
        ScoringRule(code="correct_winner_goal_difference", label="Correct Winner + GD", points=6.0, enabled=True, display_specificity_rank=2),
        ScoringRule(code="correct_winner_winner_goals", label="Correct Winner + WG", points=5.0, enabled=True, display_specificity_rank=3),
        ScoringRule(code="correct_winner_any_team_goals", label="Correct Winner + Any Team Goals", points=4.0, enabled=True, display_specificity_rank=4),
        ScoringRule(code="correct_winner_only", label="Correct Winner Only", points=3.0, enabled=True, display_specificity_rank=5),
        ScoringRule(code="correct_winner_basic_a", label="Correct Winner (A)", points=3.0, enabled=True, display_specificity_rank=6),
        ScoringRule(code="correct_winner_basic_b", label="Correct Winner (B)", points=3.0, enabled=True, display_specificity_rank=7),
        ScoringRule(code="correct_draw", label="Correct Draw", points=4.0, enabled=True, display_specificity_rank=8),
        ScoringRule(code="wrong_result_team_goal", label="Wrong Result, Team Goal", points=1.0, enabled=True, display_specificity_rank=9),
        ScoringRule(code="wrong_result", label="Wrong Result", points=0.0, enabled=True, display_specificity_rank=10),
    ]


class TestBasicFunctions:
    def test_result_home_win(self):
        assert result(2, 1) == "home_win"

    def test_result_draw(self):
        assert result(1, 1) == "draw"

    def test_result_away_win(self):
        assert result(0, 1) == "away_win"

    def test_goal_difference(self):
        assert goal_difference(3, 1) == 2
        assert goal_difference(0, 0) == 0
        assert goal_difference(1, 3) == -2

    def test_winner_goals_home(self):
        assert winner_goals(3, 1) == 3

    def test_winner_goals_away(self):
        assert winner_goals(0, 2) == 2

    def test_winner_goals_draw(self):
        assert winner_goals(1, 1) is None


class TestApplies:
    def test_exact_score_applies(self):
        assert applies("exact_score", 2, 1, 2, 1) is True

    def test_exact_score_not_applies(self):
        assert applies("exact_score", 2, 1, 2, 0) is False

    def test_correct_winner_gd_applies(self):
        # Predict 2-1, actual 3-2: same winner, same GD (+1), not exact
        assert applies("correct_winner_goal_difference", 2, 1, 3, 2) is True

    def test_correct_winner_gd_not_exact(self):
        # Exact score should NOT trigger correct_winner_goal_difference
        assert applies("correct_winner_goal_difference", 2, 1, 2, 1) is False

    def test_correct_winner_gd_draw_excluded(self):
        # Draw with same score difference (0) should not apply
        assert applies("correct_winner_goal_difference", 1, 1, 2, 2) is False

    def test_correct_winner_winner_goals(self):
        # Predict 2-0, actual 2-1: same winner, same winner goals (2), not exact
        assert applies("correct_winner_winner_goals", 2, 0, 2, 1) is True

    def test_correct_winner_winner_goals_exact_excluded(self):
        assert applies("correct_winner_winner_goals", 2, 1, 2, 1) is False

    def test_correct_winner_any_team_goals_loser_match(self):
        # Predict 3-1, actual 2-1: same winner (home), loser's goals match (1==1), not exact
        assert applies("correct_winner_any_team_goals", 3, 1, 2, 1) is True

    def test_correct_winner_any_team_goals_winner_match(self):
        # Predict 2-0, actual 2-1: same winner, winner's goals match (2==2), not exact
        assert applies("correct_winner_any_team_goals", 2, 0, 2, 1) is True

    def test_correct_winner_any_team_goals_no_goal_match(self):
        # Predict 3-1, actual 2-0: same winner but neither team's goals match
        assert applies("correct_winner_any_team_goals", 3, 1, 2, 0) is False

    def test_correct_winner_any_team_goals_wrong_winner(self):
        # Predict 1-2 (away win), actual 2-1 (home win): wrong winner, even though a goal matches
        assert applies("correct_winner_any_team_goals", 1, 2, 2, 1) is False

    def test_correct_winner_any_team_goals_exact_excluded(self):
        assert applies("correct_winner_any_team_goals", 2, 1, 2, 1) is False

    def test_correct_winner_any_team_goals_draw_excluded(self):
        # Both draws with a matching goal count must not apply (not a winner)
        assert applies("correct_winner_any_team_goals", 1, 1, 1, 2) is False

    def test_correct_winner_only_both_goals_wrong(self):
        # Predict 1-0, actual 3-1: same winner (home), neither team's goals match
        assert applies("correct_winner_only", 1, 0, 3, 1) is True

    def test_correct_winner_only_loser_match_excluded(self):
        # Predict 3-1, actual 2-1: loser's goals match (1==1) -> not "winner only"
        assert applies("correct_winner_only", 3, 1, 2, 1) is False

    def test_correct_winner_only_winner_match_excluded(self):
        # Predict 2-0, actual 2-1: winner's goals match (2==2) -> not "winner only"
        assert applies("correct_winner_only", 2, 0, 2, 1) is False

    def test_correct_winner_only_exact_excluded(self):
        # Exact score: both match, so not "winner only"
        assert applies("correct_winner_only", 2, 1, 2, 1) is False

    def test_correct_winner_only_wrong_winner_excluded(self):
        # Predict 1-2 (away win), actual 2-1 (home win): wrong winner
        assert applies("correct_winner_only", 1, 2, 2, 1) is False

    def test_correct_winner_only_draw_excluded(self):
        # Predicted draw is never a "winner" outcome
        assert applies("correct_winner_only", 1, 1, 2, 2) is False

    def test_correct_winner_basic_a(self):
        # Predict 1-0, actual 3-1: correct winner, different GD
        assert applies("correct_winner_basic_a", 1, 0, 3, 1) is True

    def test_correct_winner_basic_a_same_gd_excluded(self):
        # Same GD should NOT apply basic_a
        assert applies("correct_winner_basic_a", 2, 1, 3, 2) is False

    def test_correct_winner_basic_b(self):
        # Predict 2-0, actual 3-0: correct winner, different winner goals (2 vs 3)
        assert applies("correct_winner_basic_b", 2, 0, 3, 0) is True

    def test_correct_winner_basic_b_same_winner_goals_excluded(self):
        # Same winner goals
        assert applies("correct_winner_basic_b", 2, 0, 2, 1) is False

    def test_correct_draw(self):
        # Predict 1-1, actual 2-2: both draw, not exact
        assert applies("correct_draw", 1, 1, 2, 2) is True

    def test_correct_draw_exact_excluded(self):
        # Exact draw prediction vs exact draw actual
        assert applies("correct_draw", 1, 1, 1, 1) is False

    def test_correct_draw_wrong_result(self):
        # Predicted draw but actual was win
        assert applies("correct_draw", 1, 1, 2, 1) is False

    def test_wrong_result_team_goal(self):
        # Predicted 2-1 (home win), actual 0-1 (away win), home goals match? No (2 vs 0)
        # Away goals: 1 == 1 yes!
        assert applies("wrong_result_team_goal", 2, 1, 0, 1) is True

    def test_wrong_result_team_goal_home_match(self):
        # Predicted 1-2 (away win), actual 1-0 (home win): home goals match (1==1)
        assert applies("wrong_result_team_goal", 1, 2, 1, 0) is True

    def test_wrong_result_team_goal_no_match(self):
        # Predicted 2-1 (home), actual 0-3 (away): no goal match
        assert applies("wrong_result_team_goal", 2, 1, 0, 3) is False

    def test_wrong_result_always_applies(self):
        assert applies("wrong_result", 1, 0, 0, 2) is True
        assert applies("wrong_result", 2, 2, 1, 1) is True
        assert applies("wrong_result", 3, 1, 3, 1) is True


class TestScorePoints:
    def test_exact_score_wins(self, rules):
        # Exact score gets 10 pts
        pts = score_points(rules, 2, 1, 2, 1)
        assert pts == 10.0

    def test_correct_winner_gd_wins_over_basic(self, rules):
        # Predict 2-1, actual 3-2: GD same (+1), not exact -> 6 pts
        pts = score_points(rules, 2, 1, 3, 2)
        assert pts == 6.0

    def test_correct_winner_winner_goals(self, rules):
        # Predict 2-0, actual 2-1: winner goals same (2), GD different -> 5 pts
        pts = score_points(rules, 2, 0, 2, 1)
        assert pts == 5.0

    def test_correct_winner_any_team_goals(self, rules):
        # Predict 3-1, actual 2-1: same winner, loser's goals match (1), winner's goals differ (3 vs 2)
        # correct_winner_any_team_goals (4) applies; winner_goals (5) does not -> 4 pts
        pts = score_points(rules, 3, 1, 2, 1)
        assert pts == 4.0

    def test_winner_goals_beats_any_team_goals(self, rules):
        # Predict 2-0, actual 2-1: winner's goals match (2) -> winner_goals (5) wins over any_team (4)
        pts = score_points(rules, 2, 0, 2, 1)
        assert pts == 5.0

    def test_any_team_goals_beats_basic_winner(self, rules):
        # Predict 0-3, actual 1-3: same winner (away), loser's goals differ but... home 0 vs 1 differ,
        # away 3 vs 3 match -> winner's goals match -> 5 pts
        pts = score_points(rules, 0, 3, 1, 3)
        assert pts == 5.0
        # Predict 1-3, actual 1-2: same winner (away), loser (home) goals match (1==1),
        # winner's goals differ (3 vs 2), GD differs -> any_team (4) beats basic_b (3)
        pts = score_points(rules, 1, 3, 1, 2)
        assert pts == 4.0

    def test_correct_winner_only(self, rules):
        # Predict 1-0, actual 3-1: correct winner, neither goal matches, GD differs (1 vs 2)
        # -> correct_winner_only / basic rules all 3 pts
        pts = score_points(rules, 1, 0, 3, 1)
        assert pts == 3.0

    def test_correct_winner_only_yields_to_gd(self, rules):
        # Predict 1-0, actual 3-2: neither goal matches BUT GD matches (+1) -> GD rule wins (6)
        pts = score_points(rules, 1, 0, 3, 2)
        assert pts == 6.0

    def test_correct_draw_beats_basic(self, rules):
        # Predict 0-0, actual 1-1: draw, not exact -> 4 pts (correct_draw)
        pts = score_points(rules, 0, 0, 1, 1)
        assert pts == 4.0

    def test_correct_winner_basic_a_and_b_overlap(self, rules):
        # Predict 1-0, actual 3-0: correct winner, GD different (1 vs 3), winner goals different (1 vs 3)
        # Both basic_a and basic_b apply -> 3 pts (same points, tie)
        pts = score_points(rules, 1, 0, 3, 0)
        assert pts == 3.0

    def test_wrong_result_team_goal(self, rules):
        # Predicted 2-1 (home), actual 0-1 (away): away goals match -> 1 pt
        pts = score_points(rules, 2, 1, 0, 1)
        assert pts == 1.0

    def test_wrong_result_no_points(self, rules):
        # Predicted 2-1 (home), actual 0-3 (away): no goals match -> 0 pts
        pts = score_points(rules, 2, 1, 0, 3)
        assert pts == 0.0

    def test_disabled_rule_not_applied(self):
        rules = [
            ScoringRule(code="exact_score", label="Exact Score", points=10.0, enabled=False, display_specificity_rank=1),
            ScoringRule(code="wrong_result", label="Wrong Result", points=0.0, enabled=True, display_specificity_rank=8),
        ]
        # exact_score disabled -> should get 0
        pts = score_points(rules, 1, 0, 1, 0)
        assert pts == 0.0

    def test_exact_draw_gets_10_not_4(self, rules):
        # Predict 1-1, actual 1-1: exact score -> 10 pts (not correct_draw 4 pts)
        pts = score_points(rules, 1, 1, 1, 1)
        assert pts == 10.0

    def test_correct_winner_gd_vs_winner_goals_both_apply(self, rules):
        # Predict 3-1, actual 4-2: GD=2 matches (3-1=2, 4-2=2), winner goals different (3 vs 4)
        # correct_winner_gd (6) applies; correct_winner_winner_goals (5) does NOT (winner goals 3 != 4)
        pts = score_points(rules, 3, 1, 4, 2)
        assert pts == 6.0

    def test_both_gd_and_winner_goals_match(self, rules):
        # Predict 2-1, actual 3-2 -> GD=+1 matches, winner goals: 2 vs 3 differ
        # Only gd rule applies -> 6 pts
        pts = score_points(rules, 2, 1, 3, 2)
        assert pts == 6.0

    def test_winner_goals_not_gd(self, rules):
        # Predict 2-0, actual 2-1 -> winner goals same (2), GD different (2 vs 1)
        # only winner_goals applies -> 5 pts
        pts = score_points(rules, 2, 0, 2, 1)
        assert pts == 5.0


class TestBinaryScoring:
    def test_correct_result_and_total(self):
        # Predict 2-1 (home win, total 3), actual 3-0 (home win, total 3): both -> 2
        assert binary_score_points(2, 1, 3, 0) == 2.0

    def test_exact_score_gets_both(self):
        assert binary_score_points(2, 1, 2, 1) == 2.0

    def test_correct_result_only(self):
        # Predict 2-1 (home win, total 3), actual 1-0 (home win, total 1) -> 1 (result)
        assert binary_score_points(2, 1, 1, 0) == 1.0

    def test_correct_total_only(self):
        # Predict 2-1 (home win, total 3), actual 0-3 (away win, total 3) -> 1 (total)
        assert binary_score_points(2, 1, 0, 3) == 1.0

    def test_neither(self):
        # Predict 2-1 (home win, total 3), actual 0-2 (away win, total 2) -> 0
        assert binary_score_points(2, 1, 0, 2) == 0.0

    def test_correct_draw_counts(self):
        # Predict 1-1 (draw, total 2), actual 0-0 (draw, total 0) -> 1 (result only)
        assert binary_score_points(1, 1, 0, 0) == 1.0
        # Predict 1-1 (draw, total 2), actual 2-0 (home win, total 2) -> 1 (total only)
        assert binary_score_points(1, 1, 2, 0) == 1.0
        # Predict 1-1 (draw, total 2), actual 2-2... no. Predict 1-1, actual 0-2 (away, total 2) -> total only
        assert binary_score_points(1, 1, 0, 2) == 1.0

    def test_custom_point_values(self):
        # result worth 3, total worth 2
        assert binary_score_points(2, 1, 3, 0, result_points=3.0, total_goals_points=2.0) == 5.0
        assert binary_score_points(2, 1, 1, 0, result_points=3.0, total_goals_points=2.0) == 3.0
        assert binary_score_points(2, 1, 0, 3, result_points=3.0, total_goals_points=2.0) == 2.0


class TestDisplayLabel:
    def test_exact_score_label(self, rules):
        label = get_display_label(rules, 2, 1, 2, 1)
        assert label == "Exact Score"

    def test_correct_winner_only_label(self, rules):
        # Predict 1-0, actual 3-1: 3-pt rules tie; "Correct Winner Only" is most specific
        label = get_display_label(rules, 1, 0, 3, 1)
        assert label == "Correct Winner Only"

    def test_no_points_label(self, rules):
        disabled_rules = [
            ScoringRule(code="exact_score", label="Exact", points=10.0, enabled=False, display_specificity_rank=1),
        ]
        label = get_display_label(disabled_rules, 1, 0, 1, 0)
        assert label == "No points"

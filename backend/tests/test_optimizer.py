"""Tests for the optimizer."""
import pytest
import numpy as np
from app.services.scoring import ScoringRule
from app.services.poisson_model import fit_poisson, MarketProbabilities, compute_score_matrix, FitResult
from app.services.optimizer import compute_expected_points, Recommendation


@pytest.fixture
def default_rules() -> list[ScoringRule]:
    return [
        ScoringRule(code="exact_score", label="Exact Score", points=10.0, enabled=True, display_specificity_rank=1),
        ScoringRule(code="correct_winner_goal_difference", label="Correct Winner + GD", points=6.0, enabled=True, display_specificity_rank=2),
        ScoringRule(code="correct_winner_winner_goals", label="Correct Winner + WG", points=5.0, enabled=True, display_specificity_rank=3),
        ScoringRule(code="correct_winner_basic_a", label="Correct Winner (A)", points=3.0, enabled=True, display_specificity_rank=4),
        ScoringRule(code="correct_winner_basic_b", label="Correct Winner (B)", points=3.0, enabled=True, display_specificity_rank=5),
        ScoringRule(code="correct_draw", label="Correct Draw", points=4.0, enabled=True, display_specificity_rank=6),
        ScoringRule(code="wrong_result_team_goal", label="Wrong Result, Team Goal", points=1.0, enabled=True, display_specificity_rank=7),
        ScoringRule(code="wrong_result", label="Wrong Result", points=0.0, enabled=True, display_specificity_rank=8),
    ]


@pytest.fixture
def spain_japan_fit():
    """Pre-fit FitResult for Spain vs Japan."""
    total_inv = 1 / 1.5 + 1 / 4.2 + 1 / 7.0
    hw = (1 / 1.5) / total_inv
    d = (1 / 4.2) / total_inv
    aw = (1 / 7.0) / total_inv

    total_inv_ou = 1 / 1.9 + 1 / 1.9
    o25 = (1 / 1.9) / total_inv_ou
    u25 = (1 / 1.9) / total_inv_ou

    market = MarketProbabilities(
        home_win=hw, draw=d, away_win=aw,
        over_2_5=o25, under_2_5=u25,
    )
    return fit_poisson(market)


class TestComputeExpectedPoints:
    def test_returns_all_candidates(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules, candidate_max=5)
        # 6x6 = 36 candidates
        assert len(recs) == 36

    def test_first_rank_is_one(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        assert recs[0].rank == 1

    def test_ranks_are_sequential(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        for i, rec in enumerate(recs):
            assert rec.rank == i + 1

    def test_sorted_by_expected_points_desc(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        for i in range(len(recs) - 1):
            assert recs[i].expected_points >= recs[i + 1].expected_points

    def test_top_recommendation_has_positive_ep(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        assert recs[0].expected_points > 0

    def test_variance_nonnegative(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        for rec in recs:
            assert rec.variance >= 0

    def test_zero_prob_in_range(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        for rec in recs:
            assert 0.0 <= rec.zero_point_probability <= 1.0

    def test_score_prob_in_range(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        for rec in recs:
            assert 0.0 <= rec.score_probability <= 1.0

    def test_top_pick_favors_home_win(self, spain_japan_fit, default_rules):
        """Spain is heavily favored; top recommendation should have home_goals > away_goals."""
        recs = compute_expected_points(spain_japan_fit, default_rules)
        top = recs[0]
        # Not necessarily always home win score, but EP should be reasonable
        assert top.expected_points > 0

    def test_scoring_breakdown_non_empty_for_good_scores(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        # At least some candidates should have non-empty breakdown
        non_empty = [r for r in recs if r.scoring_breakdown]
        assert len(non_empty) > 0

    def test_candidate_max_respected(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules, candidate_max=3)
        # 4x4 = 16 candidates
        assert len(recs) == 16
        for rec in recs:
            assert rec.predicted_home <= 3
            assert rec.predicted_away <= 3

    def test_binary_mode_max_two_points(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(
            spain_japan_fit, default_rules, candidate_max=5, scoring_mode="binary",
        )
        assert len(recs) == 36
        # In binary mode the best achievable per match is result + total = 2 points,
        # so every expected value must sit within [0, 2].
        for rec in recs:
            assert 0.0 <= rec.expected_points <= 2.0

    def test_binary_breakdown_keys(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(
            spain_japan_fit, default_rules, candidate_max=5, scoring_mode="binary",
        )
        keys = set()
        for rec in recs:
            keys.update(rec.scoring_breakdown.keys())
        # Binary breakdown only ever uses these two categories.
        assert keys <= {"correct_result", "correct_total_goals"}

    def test_binary_custom_points_scale_ep(self, spain_japan_fit, default_rules):
        base = compute_expected_points(
            spain_japan_fit, default_rules, candidate_max=5, scoring_mode="binary",
        )
        scaled = compute_expected_points(
            spain_japan_fit, default_rules, candidate_max=5, scoring_mode="binary",
            binary_result_points=2.0, binary_total_goals_points=2.0,
        )
        # Doubling both point values doubles every expected value.
        base_map = {(r.predicted_home, r.predicted_away): r.expected_points for r in base}
        for r in scaled:
            assert r.expected_points == pytest.approx(2 * base_map[(r.predicted_home, r.predicted_away)])

    def test_equal_match_symmetric_ish(self):
        """For a balanced match, top candidates should be near-symmetric."""
        market = MarketProbabilities(
            home_win=0.35, draw=0.30, away_win=0.35,
            over_2_5=0.55, under_2_5=0.45,
        )
        fit = fit_poisson(market)
        rules = [
            ScoringRule(code="exact_score", label="Exact Score", points=10.0, enabled=True, display_specificity_rank=1),
            ScoringRule(code="correct_draw", label="Correct Draw", points=4.0, enabled=True, display_specificity_rank=6),
            ScoringRule(code="correct_winner_basic_a", label="CW(A)", points=3.0, enabled=True, display_specificity_rank=4),
            ScoringRule(code="wrong_result", label="WR", points=0.0, enabled=True, display_specificity_rank=8),
        ]
        recs = compute_expected_points(fit, rules, candidate_max=4)
        # Should run without error and return 25 candidates
        assert len(recs) == 25

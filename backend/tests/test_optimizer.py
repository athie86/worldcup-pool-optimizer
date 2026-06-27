"""Tests for the optimizer."""
import pytest
import numpy as np
from app.services.scoring import ScoringRule, COMBINE_BEST, COMBINE_ADDITIVE
from app.services.poisson_model import fit_poisson, MarketProbabilities, compute_score_matrix, FitResult
from app.services.optimizer import compute_expected_points, Recommendation


@pytest.fixture
def default_rules() -> list[ScoringRule]:
    """A best-match ladder using the new component catalog."""
    return [
        ScoringRule(code="exact_score", label="Exact score", points=6.0, enabled=True, display_specificity_rank=1),
        ScoringRule(code="goal_difference", label="Result + GD", points=4.0, enabled=True, display_specificity_rank=2),
        ScoringRule(code="outcome_team_goals", label="Result + team goals", points=3.0, enabled=True, display_specificity_rank=3),
        ScoringRule(code="correct_outcome", label="Correct result", points=2.0, enabled=True, display_specificity_rank=4),
        ScoringRule(code="team_goals", label="A team's goals", points=1.0, enabled=True, display_specificity_rank=5),
        ScoringRule(code="total_goals", label="Total goals", points=1.0, enabled=False, display_specificity_rank=6),
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

    def test_scoring_breakdown_non_empty_for_good_scores(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        non_empty = [r for r in recs if r.scoring_breakdown]
        assert len(non_empty) > 0

    def test_breakdown_uses_component_codes(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules)
        keys = set()
        for rec in recs:
            keys.update(rec.scoring_breakdown.keys())
        valid = {r.code for r in default_rules}
        assert keys <= valid

    def test_candidate_max_respected(self, spain_japan_fit, default_rules):
        recs = compute_expected_points(spain_japan_fit, default_rules, candidate_max=3)
        assert len(recs) == 16
        for rec in recs:
            assert rec.predicted_home <= 3
            assert rec.predicted_away <= 3

    def test_additive_mode_can_exceed_best(self, spain_japan_fit):
        """Additive mode sums components, so it can score more than best mode."""
        rules = [
            ScoringRule(code="correct_outcome", label="Result", points=3.0, enabled=True, display_specificity_rank=4),
            ScoringRule(code="total_goals", label="Total", points=1.0, enabled=True, display_specificity_rank=6),
        ]
        best = compute_expected_points(spain_japan_fit, rules, candidate_max=5, combine_mode=COMBINE_BEST)
        additive = compute_expected_points(spain_japan_fit, rules, candidate_max=5, combine_mode=COMBINE_ADDITIVE)
        best_top = max(r.expected_points for r in best)
        add_top = max(r.expected_points for r in additive)
        assert add_top >= best_top

    def test_cap_limits_expected_points(self, spain_japan_fit):
        rules = [
            ScoringRule(code="correct_outcome", label="Result", points=3.0, enabled=True, display_specificity_rank=4),
            ScoringRule(code="total_goals", label="Total", points=1.0, enabled=True, display_specificity_rank=6),
        ]
        capped = compute_expected_points(
            spain_japan_fit, rules, candidate_max=5, combine_mode=COMBINE_ADDITIVE, cap=3.0,
        )
        # No single match can yield more than the cap, so EP <= cap everywhere.
        for rec in capped:
            assert rec.expected_points <= 3.0 + 1e-9

    def test_equal_match_runs(self):
        market = MarketProbabilities(
            home_win=0.35, draw=0.30, away_win=0.35,
            over_2_5=0.55, under_2_5=0.45,
        )
        fit = fit_poisson(market)
        rules = [
            ScoringRule(code="exact_score", label="Exact score", points=6.0, enabled=True, display_specificity_rank=1),
            ScoringRule(code="correct_outcome", label="Correct result", points=3.0, enabled=True, display_specificity_rank=4),
        ]
        recs = compute_expected_points(fit, rules, candidate_max=4)
        assert len(recs) == 25

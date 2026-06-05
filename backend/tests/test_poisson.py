"""Tests for the Poisson model fitting engine."""
import pytest
import numpy as np
from app.services.poisson_model import (
    MarketProbabilities,
    compute_score_matrix,
    model_probabilities,
    fit_poisson,
    tail_mass,
    FIT_MAX_GOALS,
)


class TestScoreMatrix:
    def test_score_matrix_shape(self):
        mat = compute_score_matrix(1.5, 1.0, 10)
        assert mat.shape == (11, 11)

    def test_score_matrix_sums_to_one(self):
        mat = compute_score_matrix(1.5, 1.0, 20)
        assert abs(mat.sum() - 1.0) < 0.001

    def test_score_matrix_nonnegative(self):
        mat = compute_score_matrix(2.0, 1.5, 10)
        assert (mat >= 0).all()

    def test_score_matrix_large_lambda(self):
        mat = compute_score_matrix(4.0, 3.0, 20)
        assert abs(mat.sum() - 1.0) < 0.01


class TestModelProbabilities:
    def test_h2h_sums_to_one(self):
        probs = model_probabilities(1.5, 1.0, FIT_MAX_GOALS)
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        assert abs(total - 1.0) < 0.001

    def test_over_under_sums_to_one(self):
        probs = model_probabilities(1.5, 1.0, FIT_MAX_GOALS)
        for line in ["1.5", "2.5", "3.5"]:
            over = probs[f"over_{line.replace('.', '_')}"]
            under = probs[f"under_{line.replace('.', '_')}"]
            # Over + Under doesn't need to be exactly 1 (there's probability at exactly line)
            # but should be close
            assert abs(over + under - 1.0) < 0.01, f"Line {line}: over+under = {over+under}"

    def test_home_favored_higher_home_win(self):
        probs = model_probabilities(2.0, 0.5, FIT_MAX_GOALS)
        assert probs["home_win"] > probs["away_win"]

    def test_away_favored_higher_away_win(self):
        probs = model_probabilities(0.5, 2.0, FIT_MAX_GOALS)
        assert probs["away_win"] > probs["home_win"]

    def test_equal_lambdas_symmetry(self):
        probs = model_probabilities(1.5, 1.5, FIT_MAX_GOALS)
        assert abs(probs["home_win"] - probs["away_win"]) < 0.001


class TestFitPoisson:
    @pytest.fixture
    def spain_japan_market(self):
        """Spain vs Japan sample odds (Spain ~67% home win)."""
        # Raw odds: 1.50 / 4.20 / 7.00, O2.5=1.90/1.90
        # Implied probs (raw): 1/1.5=0.667, 1/4.2=0.238, 1/7.0=0.143 -> sum=1.048
        # Normalized: ~0.636, ~0.227, ~0.137
        total_inv = 1 / 1.5 + 1 / 4.2 + 1 / 7.0
        hw = (1 / 1.5) / total_inv
        d = (1 / 4.2) / total_inv
        aw = (1 / 7.0) / total_inv

        total_inv_ou = 1 / 1.9 + 1 / 1.9
        o25 = (1 / 1.9) / total_inv_ou
        u25 = (1 / 1.9) / total_inv_ou

        return MarketProbabilities(
            home_win=hw, draw=d, away_win=aw,
            over_2_5=o25, under_2_5=u25,
        )

    def test_fit_converges(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        assert fit.lambda_home > 0
        assert fit.lambda_away > 0

    def test_fit_lambdas_reasonable(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        # Spain is favored, so lambda_home > lambda_away
        assert fit.lambda_home > fit.lambda_away
        # Total goals around 2.5
        assert 1.5 < fit.lambda_home + fit.lambda_away < 4.0

    def test_fit_status_not_failed(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        assert fit.fit_status not in ("fit_failed", "incomplete_missing_h2h")

    def test_fit_score_matrix_shape(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        assert len(fit.score_matrix.shape) == 2
        assert fit.score_matrix.shape[0] == fit.score_matrix.shape[1]

    def test_h2h_only_weak_status(self):
        """H2H only -> weak fit status."""
        total_inv = 1 / 1.5 + 1 / 4.2 + 1 / 7.0
        hw = (1 / 1.5) / total_inv
        d = (1 / 4.2) / total_inv
        aw = (1 / 7.0) / total_inv

        market = MarketProbabilities(home_win=hw, draw=d, away_win=aw)
        fit = fit_poisson(market)
        assert fit.fit_status == "weak"

    def test_missing_h2h_returns_incomplete(self):
        market = MarketProbabilities(over_2_5=0.55, under_2_5=0.45)
        fit = fit_poisson(market)
        assert "incomplete" in fit.fit_status or fit.fit_status == "incomplete_missing_h2h"

    def test_fitted_probs_close_to_market(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        assert abs(fit.fitted_home_win - spain_japan_market.home_win) < 0.05
        assert abs(fit.fitted_draw - spain_japan_market.draw) < 0.05
        assert abs(fit.fitted_away_win - spain_japan_market.away_win) < 0.05

    def test_fitted_probs_sum_to_one(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        total = fit.fitted_home_win + fit.fitted_draw + fit.fitted_away_win
        assert abs(total - 1.0) < 0.01

    def test_diagnostics_has_rmse(self, spain_japan_market):
        fit = fit_poisson(spain_japan_market)
        assert "rmse" in fit.diagnostics

    def test_fallback_bounds_used_for_extreme_odds(self):
        """Very extreme odds that might push lambdas out of normal bounds."""
        market = MarketProbabilities(
            home_win=0.95, draw=0.03, away_win=0.02,
            over_2_5=0.80, under_2_5=0.20,
        )
        fit = fit_poisson(market)
        assert fit.lambda_home > 0
        assert fit.lambda_away > 0

    def test_balanced_match(self):
        """Equal-probability match."""
        market = MarketProbabilities(
            home_win=0.35, draw=0.30, away_win=0.35,
            over_2_5=0.55, under_2_5=0.45,
        )
        fit = fit_poisson(market)
        # Should be roughly symmetric
        assert abs(fit.lambda_home - fit.lambda_away) < 0.5

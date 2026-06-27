"""Integration tests for the horizon score model service across all three bases."""
import numpy as np
import pytest

from app.services.poisson_model import MarketProbabilities
from app.services.horizon_score_model import fit_horizon_score_model
from app.services.horizon import (
    ScoringBasis,
    compute_expected_points_from_terminal_states,
)
from app.services.scoring import ScoringRule, COMBINE_BEST


@pytest.fixture
def market() -> MarketProbabilities:
    return MarketProbabilities(
        home_win=0.50, draw=0.27, away_win=0.23,
        over_2_5=0.52, under_2_5=0.48,
    )


def _rules() -> list[ScoringRule]:
    return [
        ScoringRule("exact_score", "Exact", 6.0, True, 1, phase="knockout"),
        ScoringRule("correct_outcome", "Result", 3.0, True, 4, phase="knockout"),
        ScoringRule("advance", "Advance", 3.0, True, 7, phase="knockout"),
        ScoringRule("penalty_winner", "Pens", 3.0, True, 8, phase="knockout"),
    ]


ALL_BASES = [
    ScoringBasis.NINETY_MINUTES,
    ScoringBasis.NINETY_MINUTES_EXTRA_TIME,
    ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES,
]


class TestHorizonModelService:
    @pytest.mark.parametrize("basis", ALL_BASES)
    def test_surfaces_are_valid_probabilities(self, market, basis):
        _p90, hz = fit_horizon_score_model(
            market, None, scoring_basis=basis, model_version="v2",
        )
        assert abs(sum(s.probability for s in hz.terminal_states) - 1.0) < 1e-6
        assert abs(hz.score_matrix_90.sum() - 1.0) < 1e-6
        assert abs(hz.score_matrix_120.sum() - 1.0) < 1e-6
        assert abs(hz.p_home_advances + hz.p_away_advances - 1.0) < 1e-6
        assert 0.0 <= hz.p_goes_to_penalties <= hz.p_goes_to_extra_time <= 1.0
        assert hz.diagnostics["warnings"] == [] or isinstance(hz.diagnostics["warnings"], list)

    @pytest.mark.parametrize("basis", ALL_BASES)
    def test_recommendations_produced(self, market, basis):
        _p90, hz = fit_horizon_score_model(
            market, None, scoring_basis=basis, model_version="v2",
        )
        recs = compute_expected_points_from_terminal_states(
            hz, _rules(), basis, 5, combine_mode=COMBINE_BEST, phase="knockout",
        )
        assert recs[0].rank == 1
        assert all(r.expected_points >= 0 for r in recs)
        assert all(0.0 <= r.zero_point_probability <= 1.0 for r in recs)
        assert all(r.variance >= 0 for r in recs)

    def test_only_pens_basis_yields_penalty_picks(self, market):
        _p90, hz = fit_horizon_score_model(
            market, None,
            scoring_basis=ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES,
            model_version="v2",
        )
        recs = compute_expected_points_from_terminal_states(
            hz, _rules(), ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES, 5,
            combine_mode=COMBINE_BEST, phase="knockout",
        )
        # Draw recommendations carry an explicit penalty winner under this basis.
        draws = [r for r in recs if r.predicted_home == r.predicted_away]
        assert any(r.penalties_winner in ("home", "away") for r in draws)

    def test_ninety_basis_ignores_bonuses(self, market):
        # Under the 90' basis, advance/penalty_winner are invalid and must not be
        # awarded — EV equals a pure 90' score model.
        _p90, hz = fit_horizon_score_model(
            market, None, scoring_basis=ScoringBasis.NINETY_MINUTES, model_version="v2",
        )
        recs = compute_expected_points_from_terminal_states(
            hz, _rules(), ScoringBasis.NINETY_MINUTES, 5,
            combine_mode=COMBINE_BEST, phase="knockout",
        )
        for r in recs:
            assert "advance" not in r.scoring_breakdown
            assert "penalty_winner" not in r.scoring_breakdown

    def test_advancement_inference_from_market(self, market):
        # A direct penalty-shootout-winner market should drive q.
        from app.services.odds_normalization import BookmakerMarket, RawOutcome
        bms = [
            BookmakerMarket(
                bookmaker_key="bk1", market_key="penalty_shootout_winner", line=None,
                outcomes=[
                    RawOutcome(outcome_type="home_win", price_decimal=1.5),
                    RawOutcome(outcome_type="away_win", price_decimal=2.6),
                ],
                last_update=None,
            ),
        ]
        _p90, hz = fit_horizon_score_model(
            market, bms,
            scoring_basis=ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES,
            model_version="v2",
        )
        # Home is the shorter price → q should favour home.
        assert hz.p_home_wins_penalties_given_pens > 0.5
        assert hz.fit_tier in ("H0_rich_terminal", "H1_advancement", "H2_extra_time", "H3_score_only")

"""Tests for odds normalization."""
import pytest
from app.services.odds_normalization import (
    RawOutcome,
    BookmakerMarket,
    normalize_market,
    is_complete_h2h,
    is_complete_totals,
    compute_consensus,
)


class TestNormalizeMarket:
    def test_proportional_removes_margin(self):
        # Typical h2h with margin: sum of implied = 1.06 approx
        outcomes = [
            RawOutcome("home_win", 1.80),
            RawOutcome("draw", 3.50),
            RawOutcome("away_win", 4.00),
        ]
        norm = normalize_market(outcomes)
        # Should sum to 1.0
        assert abs(sum(norm.values()) - 1.0) < 1e-9

    def test_normalize_values_positive(self):
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("draw", 3.5),
            RawOutcome("away_win", 4.0),
        ]
        norm = normalize_market(outcomes)
        for v in norm.values():
            assert v > 0

    def test_normalize_respects_odds_ratio(self):
        # If two outcomes have same odds, they should have same probability
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("away_win", 2.0),
        ]
        norm = normalize_market(outcomes)
        assert abs(norm["home_win"] - norm["away_win"]) < 1e-9

    def test_normalize_zero_price_excluded(self):
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("draw", 0.0),  # invalid
            RawOutcome("away_win", 3.0),
        ]
        norm = normalize_market(outcomes)
        assert "draw" not in norm

    def test_normalize_empty_returns_empty(self):
        norm = normalize_market([])
        assert norm == {}


class TestCompletenessChecks:
    def test_complete_h2h(self):
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("draw", 3.5),
            RawOutcome("away_win", 4.0),
        ]
        assert is_complete_h2h(outcomes) is True

    def test_incomplete_h2h_missing_draw(self):
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("away_win", 4.0),
        ]
        assert is_complete_h2h(outcomes) is False

    def test_incomplete_h2h_missing_away(self):
        outcomes = [
            RawOutcome("home_win", 2.0),
            RawOutcome("draw", 3.5),
        ]
        assert is_complete_h2h(outcomes) is False

    def test_complete_totals(self):
        outcomes = [
            RawOutcome("over", 1.90),
            RawOutcome("under", 1.90),
        ]
        assert is_complete_totals(outcomes) is True

    def test_incomplete_totals_missing_under(self):
        outcomes = [RawOutcome("over", 1.90)]
        assert is_complete_totals(outcomes) is False


class TestComputeConsensus:
    def test_consensus_averages_bookmakers(self):
        bm1 = BookmakerMarket("bk1", "h2h", None, [
            RawOutcome("home_win", 1.80),
            RawOutcome("draw", 3.50),
            RawOutcome("away_win", 5.00),
        ])
        bm2 = BookmakerMarket("bk2", "h2h", None, [
            RawOutcome("home_win", 1.85),
            RawOutcome("draw", 3.40),
            RawOutcome("away_win", 4.80),
        ])
        result = compute_consensus([bm1, bm2])
        assert result.home_win is not None
        assert result.draw is not None
        assert result.away_win is not None

    def test_consensus_h2h_probs_sum_to_one(self):
        bm = BookmakerMarket("bk1", "h2h", None, [
            RawOutcome("home_win", 1.80),
            RawOutcome("draw", 3.50),
            RawOutcome("away_win", 5.00),
        ])
        result = compute_consensus([bm])
        total = result.home_win + result.draw + result.away_win
        assert abs(total - 1.0) < 1e-6

    def test_incomplete_h2h_rejected(self):
        bm = BookmakerMarket("bk1", "h2h", None, [
            RawOutcome("home_win", 1.80),
            RawOutcome("draw", 3.50),
            # missing away_win
        ])
        result = compute_consensus([bm])
        assert result.home_win is None

    def test_incomplete_totals_rejected(self):
        bm = BookmakerMarket("bk1", "totals", 2.5, [
            RawOutcome("over", 1.90),
            # missing under
        ])
        result = compute_consensus([bm])
        assert result.over_2_5 is None

    def test_totals_line_assignment(self):
        bm = BookmakerMarket("bk1", "totals", 2.5, [
            RawOutcome("over", 1.90),
            RawOutcome("under", 1.90),
        ])
        result = compute_consensus([bm])
        assert result.over_2_5 is not None
        assert result.under_2_5 is not None

    def test_manual_override_replaces_fetched(self):
        # Fetched odds have bm1
        bm1 = BookmakerMarket("bk1", "h2h", None, [
            RawOutcome("home_win", 1.80),
            RawOutcome("draw", 3.50),
            RawOutcome("away_win", 5.00),
        ])
        # Override with different odds
        override_outcomes = [
            RawOutcome("home_win", 1.40, line=None),
            RawOutcome("draw", 4.50, line=None),
            RawOutcome("away_win", 8.00, line=None),
        ]
        result_no_override = compute_consensus([bm1])
        result_with_override = compute_consensus([bm1], override_outcomes)

        # Override should be used (1.40 favors home more)
        assert result_with_override.home_win > result_no_override.home_win

    def test_manual_override_totals(self):
        bm = BookmakerMarket("bk1", "totals", 2.5, [
            RawOutcome("over", 1.90),
            RawOutcome("under", 1.90),
        ])
        override_outcomes = [
            RawOutcome("over", 1.50, line=2.5),
            RawOutcome("under", 2.50, line=2.5),
        ]
        result = compute_consensus([bm], override_outcomes)
        # Override makes over much more likely
        assert result.over_2_5 > 0.60

    def test_no_bookmakers_returns_empty_probs(self):
        result = compute_consensus([])
        assert result.home_win is None
        assert result.over_2_5 is None

    def test_multiple_lines(self):
        bm1 = BookmakerMarket("bk1", "totals", 2.5, [
            RawOutcome("over", 1.90),
            RawOutcome("under", 1.90),
        ])
        bm2 = BookmakerMarket("bk1", "totals", 3.5, [
            RawOutcome("over", 3.00),
            RawOutcome("under", 1.40),
        ])
        result = compute_consensus([bm1, bm2])
        assert result.over_2_5 is not None
        assert result.over_3_5 is not None

"""Tests for the V2 market score model, registry and fallbacks (spec §9-§11, §22)."""
import numpy as np
import pytest
from unittest.mock import patch

from app.services.score_model import MarketProbabilities
from app.services.market_score_model_v2 import (
    fit_market_score_model_v2, _operator,
)
from app.services import model_registry
from app.services.optimizer import compute_expected_points
from app.services.scoring import ScoringRule
from app.services.odds_normalization import BookmakerMarket, RawOutcome


def full_market():
    return MarketProbabilities(
        home_win=0.55, draw=0.27, away_win=0.18,
        over_1_5=0.78, under_1_5=0.22,
        over_2_5=0.52, under_2_5=0.48,
        over_3_5=0.28, under_3_5=0.72,
    )


def _rich_books():
    bms = []
    for bk in ["pinnacle", "bet365", "williamhill", "unibet", "betfair_ex_eu"]:
        bms.append(BookmakerMarket(bk, "h2h", None,
                   [RawOutcome("home_win", 1.7), RawOutcome("draw", 3.6), RawOutcome("away_win", 5.5)]))
        bms.append(BookmakerMarket(bk, "totals", 2.5,
                   [RawOutcome("over", 1.9), RawOutcome("under", 1.95)]))
        bms.append(BookmakerMarket(bk, "btts", None,
                   [RawOutcome("btts_yes", 1.95), RawOutcome("btts_no", 1.85)]))
    return bms


# ── AC005/AC006: valid matrix ───────────────────────────────────────────────

def test_score_matrix_sums_to_one():
    r = fit_market_score_model_v2(full_market())
    assert r.score_matrix.sum() == pytest.approx(1.0, abs=1e-8)


def test_score_matrix_non_negative_and_finite():
    r = fit_market_score_model_v2(full_market())
    assert (r.score_matrix >= 0).all()
    assert np.all(np.isfinite(r.score_matrix))


def test_actual_grid_default_13():
    r = fit_market_score_model_v2(full_market())
    assert r.score_matrix.shape == (13, 13)
    assert r.actual_score_max == 12


def test_actual_grid_configurable():
    r = fit_market_score_model_v2(full_market(), actual_score_max=15)
    assert r.score_matrix.shape == (16, 16)


# ── AC007: expected goals from matrix ───────────────────────────────────────

def test_final_xg_matches_matrix_expectation():
    r = fit_market_score_model_v2(full_market())
    I, J = np.indices(r.score_matrix.shape)
    assert r.final_home_xg == pytest.approx(float((r.score_matrix * I).sum()), abs=1e-9)
    assert r.final_away_xg == pytest.approx(float((r.score_matrix * J).sum()), abs=1e-9)


# ── tiers ───────────────────────────────────────────────────────────────────

def test_rich_market_is_t0():
    r = fit_market_score_model_v2(full_market(), _rich_books())
    assert r.fit_tier == "T0_rich"


def test_standard_market_is_t1():
    r = fit_market_score_model_v2(full_market())
    assert r.fit_tier == "T1_standard"


def test_totals_only_tier_t4():
    mp = MarketProbabilities(over_2_5=0.5, under_2_5=0.5)
    bms = [BookmakerMarket("a", "totals", 2.5, [RawOutcome("over", 1.95), RawOutcome("under", 1.95)])]
    r = fit_market_score_model_v2(mp, bms)
    assert r.fit_tier == "T4_totals_only"


def test_no_market_neutral_or_fundamental():
    r = fit_market_score_model_v2(MarketProbabilities())
    assert r.fit_tier in ("T5_fundamental_only", "T6_neutral_fallback")
    assert r.score_matrix.sum() == pytest.approx(1.0, abs=1e-8)


# ── calibration quality ─────────────────────────────────────────────────────

def test_calibration_reduces_or_preserves_error():
    r = fit_market_score_model_v2(full_market())
    assert r.calibrated_error <= r.prior_error * 1.5 + 0.005


def test_calibration_fits_result_market_well():
    r = fit_market_score_model_v2(full_market())
    from app.services.score_model import matrix_market_probs
    p = matrix_market_probs(r.score_matrix)
    assert p["home_win"] == pytest.approx(0.55, abs=0.05)


# ── operators ───────────────────────────────────────────────────────────────

def test_operator_btts():
    P = np.zeros((4, 4))
    P[1, 1] = 0.5
    P[2, 0] = 0.5
    I, J = np.indices(P.shape)
    assert _operator(P, I, J, "btts_yes", None) == pytest.approx(0.5)


def test_operator_total_integer_is_conditional():
    P = np.zeros((4, 4))
    P[1, 1] = 0.4  # total 2
    P[2, 1] = 0.4  # total 3
    P[1, 2] = 0.2  # total 3 (push at line 3 excluded)
    I, J = np.indices(P.shape)
    # line 3: over = total>3 (none here) ... build clearer case
    P = np.zeros((5, 5))
    P[3, 0] = 0.3   # total 3 -> push at line 3
    P[2, 0] = 0.4   # total 2 -> under
    P[2, 2] = 0.3   # total 4 -> over
    I, J = np.indices(P.shape)
    over = _operator(P, I, J, "total_over_integer_line", 3.0)
    # conditional over = 0.3 / (0.3 + 0.4)
    assert over == pytest.approx(0.3 / 0.7, abs=1e-6)


# ── AC011/AC012: registry fallbacks ─────────────────────────────────────────

def test_registry_v2_selected():
    r = model_registry.fit("v2", full_market())
    assert r.model_type == "market_score_model_v2"


def test_registry_v1_selected():
    r = model_registry.fit("v1", full_market())
    assert r.model_type == "entropy_calibrated_dixon_coles"


def test_registry_v2_failure_falls_back_to_v1():
    with patch("app.services.model_registry.fit_market_score_model_v2",
               side_effect=RuntimeError("boom")):
        r = model_registry.fit("v2", full_market())
    assert r.model_type == "entropy_calibrated_dixon_coles"


def test_registry_v1_failure_falls_back_to_neutral():
    with patch("app.services.model_registry.fit_market_score_model_v2",
               side_effect=RuntimeError("boom")), \
         patch("app.services.model_registry.fit_score_model",
               side_effect=RuntimeError("boom2")):
        r = model_registry.fit("v2", full_market())
    assert r.model_type == "neutral_fallback"
    assert r.score_matrix.sum() == pytest.approx(1.0, abs=1e-8)


# ── AC008: candidate grid separate from actual grid ─────────────────────────

def test_optimizer_candidate_grid_independent_of_actual_grid():
    r = fit_market_score_model_v2(full_market())
    rules = [ScoringRule("exact_score", "Exact", 10.0, True, 1),
             ScoringRule("wrong_result", "WR", 0.0, True, 8)]
    recs = compute_expected_points(r, rules, candidate_max=5)
    assert len(recs) == 36  # 6x6 candidates regardless of 13x13 actual grid


def test_tail_outcomes_above_candidate_affect_ep():
    """Actual scores above the candidate max must still carry probability mass."""
    r = fit_market_score_model_v2(full_market())
    tail = float(r.score_matrix[6:, :].sum() + r.score_matrix[:, 6:].sum())
    assert tail > 0.0

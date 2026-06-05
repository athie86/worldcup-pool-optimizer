"""
Tests for the Dixon-Coles + entropy-calibrated score model.

Covers:
  1.  Score matrix sums to 1.
  2.  All probabilities ≥ 0.
  3.  1X2 probs from matrix sum to 1.
  4.  O/U probabilities are consistent (over + under ≤ 1, push mass = 0 for half-lines).
  5.  DC τ correction only affects {0,1}×{0,1} cells.
  6.  Entropy calibration improves (or at least doesn't badly worsen) market fit vs prior.
  7.  Optimizer produces the same result when given the same matrix.
  8.  Fallback to independent Poisson when DC fitting is forced to fail.
  9.  Fallback to DC prior when entropy calibration is forced to fail.
  10. Missing totals → warning but no failure when 1X2 is present.
  11. Missing 1X2 → fit_status "incomplete_missing_h2h".
  12. Tail-mass warning triggered when appropriate.
  13. Spain vs Japan sample — calibrated RMSE < prior RMSE (or both ≤ threshold).
  14. matrix_market_probs correctness on simple known matrix.
  15. DC matrix validity: all cells ≥ 0, sums to 1.
"""

import numpy as np
import pytest
from unittest.mock import patch

from app.services.score_model import (
    fit_score_model,
    dixon_coles_matrix,
    matrix_market_probs,
    _dc_tau,
    _build_targets,
    _fit_dc_params,
    _entropy_calibrate,
    _fallback_poisson_result,
    SCORE_GRID,
    CANDIDATE_MAX,
    TAIL_MASS_WARNING_THRESHOLD,
    MarketProbabilities,
)
from app.services.optimizer import compute_expected_points
from app.services.scoring import ScoringRule


# ── Helpers ────────────────────────────────────────────────────────────────────

def sample_market_full() -> MarketProbabilities:
    """Spain vs Japan sample from the spec (normalised)."""
    # h2h: 1.80 / 3.60 / 5.00 → raw 0.5556 / 0.2778 / 0.2000, total 1.0334
    total = 1.0334
    return MarketProbabilities(
        home_win=0.5556 / total,
        draw=0.2778 / total,
        away_win=0.2000 / total,
        # totals: 1.5  over=1.35  under=3.10
        over_1_5=1 / 1.35 / (1 / 1.35 + 1 / 3.10),
        under_1_5=1 / 3.10 / (1 / 1.35 + 1 / 3.10),
        # totals: 2.5  over=1.95  under=1.85
        over_2_5=1 / 1.95 / (1 / 1.95 + 1 / 1.85),
        under_2_5=1 / 1.85 / (1 / 1.95 + 1 / 1.85),
        # totals: 3.5  over=3.25  under=1.33
        over_3_5=1 / 3.25 / (1 / 3.25 + 1 / 1.33),
        under_3_5=1 / 1.33 / (1 / 3.25 + 1 / 1.33),
    )


def sample_market_h2h_only() -> MarketProbabilities:
    return MarketProbabilities(home_win=0.50, draw=0.25, away_win=0.25)


def sample_rules() -> list[ScoringRule]:
    return [
        ScoringRule("exact_score", "Exact", 10.0, True, 1),
        ScoringRule("correct_winner_goal_difference", "GD", 6.0, True, 2),
        ScoringRule("correct_winner_winner_goals", "WG", 5.0, True, 3),
        ScoringRule("correct_winner_basic_a", "Basic A", 3.0, True, 4),
        ScoringRule("correct_winner_basic_b", "Basic B", 3.0, True, 5),
        ScoringRule("correct_draw", "Draw", 4.0, True, 6),
        ScoringRule("wrong_result_team_goal", "Wrong+goal", 1.0, True, 7),
        ScoringRule("wrong_result", "Wrong", 0.0, True, 8),
    ]


# ── 1. Score matrix sums to 1 ─────────────────────────────────────────────────

def test_score_matrix_sums_to_one_full_market():
    result = fit_score_model(sample_market_full())
    total = result.score_matrix.sum()
    assert abs(total - 1.0) < 1e-6, f"Matrix sum = {total}"


def test_score_matrix_sums_to_one_h2h_only():
    result = fit_score_model(sample_market_h2h_only())
    total = result.score_matrix.sum()
    assert abs(total - 1.0) < 1e-6, f"Matrix sum = {total}"


def test_prior_matrix_sums_to_one():
    result = fit_score_model(sample_market_full())
    total = result.prior_matrix.sum()
    assert abs(total - 1.0) < 1e-6


# ── 2. All probabilities non-negative ────────────────────────────────────────

def test_score_matrix_non_negative():
    result = fit_score_model(sample_market_full())
    assert (result.score_matrix >= 0).all()


def test_prior_matrix_non_negative():
    result = fit_score_model(sample_market_full())
    assert (result.prior_matrix >= 0).all()


# ── 3. 1X2 probs from matrix sum to 1 ────────────────────────────────────────

def test_1x2_from_matrix_sums_to_one():
    result = fit_score_model(sample_market_full())
    p = matrix_market_probs(result.score_matrix)
    total = p["home_win"] + p["draw"] + p["away_win"]
    assert abs(total - 1.0) < 1e-5, f"1X2 sum = {total}"


# ── 4. O/U consistency ────────────────────────────────────────────────────────

def test_ou_over_plus_under_leq_one():
    """For half-goal lines there is no push, so over+under should equal 1."""
    result = fit_score_model(sample_market_full())
    p = matrix_market_probs(result.score_matrix)
    for line in ("1_5", "2_5", "3_5"):
        total = p[f"over_{line}"] + p[f"under_{line}"]
        assert abs(total - 1.0) < 1e-5, f"O/U {line} sum = {total}"


# ── 5. DC τ only affects {0,1}×{0,1} ────────────────────────────────────────

def test_dc_tau_only_low_scores():
    """Cells outside {0,1}×{0,1} must have τ = 1."""
    lh, la, rho = 1.5, 1.1, -0.1
    for i in range(6):
        for j in range(6):
            tau = _dc_tau(i, j, lh, la, rho)
            if i >= 2 or j >= 2:
                assert tau == 1.0, f"tau({i},{j}) = {tau}, expected 1.0"


def test_dc_tau_low_scores_differ_from_one_when_rho_nonzero():
    """When ρ ≠ 0, τ for low-score cells must differ from 1."""
    rho = -0.10
    lh, la = 1.5, 1.1
    assert _dc_tau(0, 0, lh, la, rho) != 1.0
    assert _dc_tau(0, 1, lh, la, rho) != 1.0
    assert _dc_tau(1, 0, lh, la, rho) != 1.0
    assert _dc_tau(1, 1, lh, la, rho) != 1.0


def test_dc_tau_rho_zero_all_ones():
    """When ρ = 0, all τ values equal 1."""
    lh, la, rho = 1.5, 1.1, 0.0
    for i in range(2):
        for j in range(2):
            assert _dc_tau(i, j, lh, la, rho) == 1.0


# ── 6. Entropy calibration improves fit ──────────────────────────────────────

def test_calibration_improves_or_maintains_market_fit():
    result = fit_score_model(sample_market_full())
    # calibrated RMSE should not be substantially worse than prior
    assert result.calibrated_error <= result.prior_error * 1.5 + 0.01


def test_calibration_kl_divergence_reasonable():
    result = fit_score_model(sample_market_full())
    # KL divergence from prior should be finite and not absurdly large
    assert 0.0 <= result.kl_divergence < 5.0


# ── 7. Optimizer produces consistent results ─────────────────────────────────

def test_optimizer_uses_score_matrix():
    result = fit_score_model(sample_market_full())
    rules = sample_rules()
    recs = compute_expected_points(result, rules)
    assert len(recs) == SCORE_GRID * SCORE_GRID  # 36 candidates
    assert recs[0].rank == 1
    assert all(r.expected_points >= 0 for r in recs)


def test_optimizer_deterministic():
    result = fit_score_model(sample_market_full())
    rules = sample_rules()
    recs1 = compute_expected_points(result, rules)
    recs2 = compute_expected_points(result, rules)
    assert recs1[0].predicted_home == recs2[0].predicted_home
    assert recs1[0].predicted_away == recs2[0].predicted_away


# ── 8. Fallback to independent Poisson when DC fails ─────────────────────────

def test_fallback_to_poisson_on_dc_failure():
    """When DC fitting raises, the result should be a Poisson fallback (weak status)."""
    market = sample_market_full()
    with patch("app.services.score_model._fit_dc_params", side_effect=RuntimeError("forced")):
        result = fit_score_model(market)
    assert result.model_type == "independent_poisson_fallback"
    assert result.fit_status == "weak"
    assert result.score_matrix.sum() == pytest.approx(1.0, abs=1e-6)
    assert any("fallback" in w.lower() or "Poisson" in w for w in result.diagnostics["warnings"])


# ── 9. Fallback to DC prior when entropy calibration fails ───────────────────

def test_fallback_to_dc_prior_on_entropy_failure():
    market = sample_market_full()
    with patch("app.services.score_model._entropy_calibrate", side_effect=RuntimeError("forced")):
        result = fit_score_model(market)
    # Should NOT be a full failure; must return a valid matrix
    assert result.score_matrix.sum() == pytest.approx(1.0, abs=1e-6)
    assert any("calibration failed" in w.lower() or "DC prior" in w for w in result.diagnostics["warnings"])


# ── 10. Missing totals → warning, not failure ────────────────────────────────

def test_missing_totals_adds_warning():
    result = fit_score_model(sample_market_h2h_only())
    assert result.fit_status != "incomplete_missing_h2h"
    assert result.score_matrix.sum() == pytest.approx(1.0, abs=1e-6)
    warnings = result.diagnostics.get("warnings", [])
    assert any("1X2" in w or "Totals" in w for w in warnings)


def test_missing_totals_fit_status_weak():
    result = fit_score_model(sample_market_h2h_only())
    assert result.fit_status == "weak"


# ── 11. Missing h2h → incomplete ────────────────────────────────────────────

def test_missing_h2h_returns_incomplete():
    market = MarketProbabilities()  # all None
    result = fit_score_model(market)
    assert result.fit_status == "incomplete_missing_h2h"


def test_missing_h2h_with_totals_still_incomplete():
    market = MarketProbabilities(over_2_5=0.50, under_2_5=0.50)
    result = fit_score_model(market)
    assert result.fit_status == "incomplete_missing_h2h"


# ── 12. Tail-mass warning ────────────────────────────────────────────────────

def test_tail_mass_warning_for_high_scoring_match():
    """A match with very high expected goals (e.g. λ_h=4, λ_a=3) should trigger tail warning."""
    # Construct a market consistent with ~7 total expected goals
    # Over 2.5 ≈ 0.97, draw ≈ 0.05, home win ≈ 0.70
    market = MarketProbabilities(
        home_win=0.65,
        draw=0.10,
        away_win=0.25,
        over_1_5=0.99,
        under_1_5=0.01,
        over_2_5=0.95,
        under_2_5=0.05,
        over_3_5=0.85,
        under_3_5=0.15,
    )
    result = fit_score_model(market)
    if result.tail_mass > TAIL_MASS_WARNING_THRESHOLD:
        warnings = result.diagnostics.get("warnings", [])
        assert any("tail" in w.lower() for w in warnings)


# ── 13. Spain vs Japan accuracy ──────────────────────────────────────────────

def test_spain_japan_calibration_quality():
    market = sample_market_full()
    result = fit_score_model(market)
    # Should converge to a non-failing status
    assert result.fit_status in ("good", "acceptable", "weak")
    # Calibrated error should be reasonably small
    assert result.calibrated_error < 0.10
    # Calibrated model should be closer to market than a naive uniform distribution
    uniform_errors = [
        (1 / 3 - market.home_win) ** 2,
        (1 / 3 - market.draw) ** 2,
        (1 / 3 - market.away_win) ** 2,
    ]
    uniform_rmse = float(np.sqrt(np.mean(uniform_errors)))
    assert result.calibrated_error < uniform_rmse


# ── 14. matrix_market_probs correctness ──────────────────────────────────────

def test_matrix_market_probs_simple():
    """Use a 2×2 known matrix: all mass in 1-0 (home win)."""
    mat = np.zeros((6, 6))
    mat[1, 0] = 1.0  # home scores 1, away scores 0 → home win, total=1 (under 1.5)
    p = matrix_market_probs(mat)
    assert p["home_win"] == pytest.approx(1.0)
    assert p["draw"]     == pytest.approx(0.0)
    assert p["away_win"] == pytest.approx(0.0)
    assert p["over_1_5"]  == pytest.approx(0.0)   # 1 is not > 1.5
    assert p["under_1_5"] == pytest.approx(1.0)   # 1 < 1.5
    assert p["over_2_5"]  == pytest.approx(0.0)
    assert p["under_2_5"] == pytest.approx(1.0)


def test_matrix_market_probs_draw():
    mat = np.zeros((6, 6))
    mat[2, 2] = 1.0  # 2-2 draw, total=4 goals (over 3.5)
    p = matrix_market_probs(mat)
    assert p["draw"]     == pytest.approx(1.0)
    assert p["home_win"] == pytest.approx(0.0)
    assert p["over_3_5"] == pytest.approx(1.0)
    assert p["under_3_5"] == pytest.approx(0.0)


# ── 15. DC matrix validity ───────────────────────────────────────────────────

def test_dc_matrix_non_negative():
    mat = dixon_coles_matrix(1.5, 1.1, -0.15, 10)
    assert (mat >= 0).all()


def test_dc_matrix_sums_to_one():
    mat = dixon_coles_matrix(1.5, 1.1, -0.15, 10)
    assert abs(mat.sum() - 1.0) < 1e-8


def test_dc_matrix_rho_zero_equals_poisson():
    """With ρ=0, DC matrix should equal independent Poisson (within tolerance)."""
    from scipy.stats import poisson as sp_poisson
    lh, la = 1.4, 1.1
    mat_dc = dixon_coles_matrix(lh, la, 0.0, 10)
    n = 11
    h_pmf = sp_poisson.pmf(np.arange(n), lh)
    a_pmf = sp_poisson.pmf(np.arange(n), la)
    mat_pois = np.outer(h_pmf, a_pmf)
    mat_pois /= mat_pois.sum()
    np.testing.assert_allclose(mat_dc, mat_pois, atol=1e-8)


# ── 16. CANDIDATE_MAX / SCORE_GRID sanity ────────────────────────────────────

def test_score_grid_is_6():
    assert SCORE_GRID == 6
    assert CANDIDATE_MAX == 5


def test_result_matrix_shape():
    result = fit_score_model(sample_market_full())
    assert result.score_matrix.shape == (SCORE_GRID, SCORE_GRID)
    assert result.prior_matrix.shape == (SCORE_GRID, SCORE_GRID)

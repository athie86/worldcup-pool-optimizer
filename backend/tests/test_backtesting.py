"""Tests for the backtesting metrics and model comparison (spec §18, AC015)."""
import numpy as np
import pytest

from app.services import backtesting as bt
from app.services.score_prior import neutral_prior


def _peaked(home, away, n=13):
    m = np.full((n, n), 1e-6)
    m[home, away] = 1.0
    return m / m.sum()


def test_result_probabilities_sum_to_one():
    hw, dw, aw = bt.result_probabilities(neutral_prior(12))
    assert hw + dw + aw == pytest.approx(1.0, abs=1e-9)


def test_log_loss_lower_for_confident_correct():
    confident = bt.result_log_loss(_peaked(2, 0), 2, 0)
    flat = bt.result_log_loss(neutral_prior(12), 2, 0)
    assert confident < flat


def test_exact_score_log_score_rewards_hit():
    hit = bt.exact_score_log_score(_peaked(1, 1), 1, 1)
    miss = bt.exact_score_log_score(_peaked(1, 1), 3, 0)
    assert hit < miss


def test_top_k_hit():
    assert bt.top_k_hit(_peaked(2, 1), 2, 1, k=3)
    assert not bt.top_k_hit(_peaked(2, 1), 5, 5, k=3)


def test_total_goals_rps_nonnegative():
    assert bt.total_goals_rps(neutral_prior(12), 3) >= 0.0


def test_evaluate_and_compare_models():
    samples_good = [bt.BacktestSample(_peaked(2, 0), 2, 0),
                    bt.BacktestSample(_peaked(1, 1), 1, 1)]
    samples_bad = [bt.BacktestSample(neutral_prior(12), 2, 0),
                   bt.BacktestSample(neutral_prior(12), 1, 1)]
    cmp = bt.compare_models({"good": samples_good, "bad": samples_bad})
    assert cmp.metrics_by_model["good"]["n"] == 2
    # the confident-correct model should win the log-loss metric
    assert cmp.best_by_metric["result_log_loss"] == "good"
    assert cmp.best_by_metric["top_3_hit_rate"] == "good"


def test_evaluate_empty():
    m = bt.evaluate([])
    assert m.n == 0

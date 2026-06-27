"""
Backtesting and model-comparison metrics  (spec WCPO-PRED-MODEL-V2 §18).

Pure-function metrics over (predicted score matrix, actual score) pairs, plus a
comparison helper that scores any number of named models on the same fixtures.
Data ingestion (historical odds / scores endpoints) is intentionally decoupled:
callers supply already-fitted matrices, so this works whether the historical
plan is available or predictions are imported from CSV (spec R006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

EPS = 1e-12


def _result_index(home: int, away: int) -> int:
    return 0 if home > away else (1 if home == away else 2)


def result_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    I, J = np.indices(matrix.shape)
    hw = float(matrix[I > J].sum())
    dw = float(np.trace(matrix))
    aw = float(matrix[I < J].sum())
    return hw, dw, aw


def result_log_loss(matrix: np.ndarray, actual_home: int, actual_away: int) -> float:
    probs = result_probabilities(matrix)
    p = max(EPS, probs[_result_index(actual_home, actual_away)])
    return float(-np.log(p))


def result_brier(matrix: np.ndarray, actual_home: int, actual_away: int) -> float:
    probs = np.array(result_probabilities(matrix))
    target = np.zeros(3)
    target[_result_index(actual_home, actual_away)] = 1.0
    return float(np.sum((probs - target) ** 2))


def exact_score_log_score(matrix: np.ndarray, actual_home: int, actual_away: int) -> float:
    n = matrix.shape[0]
    if 0 <= actual_home < n and 0 <= actual_away < n:
        p = max(EPS, float(matrix[actual_home, actual_away]))
    else:
        p = EPS  # outcome outside the grid
    return float(-np.log(p))


def total_goals_rps(matrix: np.ndarray, actual_total: int) -> float:
    """Ranked probability score over the total-goals distribution."""
    n = matrix.shape[0]
    max_total = 2 * (n - 1)
    dist = np.zeros(max_total + 1)
    I, J = np.indices(matrix.shape)
    T = (I + J).ravel()
    for t, p in zip(T, matrix.ravel()):
        dist[t] += p
    cdf = np.cumsum(dist)
    actual_cdf = (np.arange(max_total + 1) >= actual_total).astype(float)
    return float(np.sum((cdf - actual_cdf) ** 2) / max_total)


def top_k_hit(matrix: np.ndarray, actual_home: int, actual_away: int, k: int = 3) -> bool:
    """Did the actual score fall in the model's top-k most-likely scores?"""
    flat = [(matrix[i, j], i, j) for i in range(matrix.shape[0]) for j in range(matrix.shape[1])]
    flat.sort(reverse=True)
    top = {(i, j) for _, i, j in flat[:k]}
    return (actual_home, actual_away) in top


@dataclass
class BacktestSample:
    matrix: np.ndarray
    actual_home: int
    actual_away: int


@dataclass
class BacktestMetrics:
    n: int
    result_log_loss: float
    result_brier: float
    exact_score_log_score: float
    total_goals_rps: float
    top_3_hit_rate: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "result_log_loss": self.result_log_loss,
            "result_brier": self.result_brier,
            "exact_score_log_score": self.exact_score_log_score,
            "total_goals_rps": self.total_goals_rps,
            "top_3_hit_rate": self.top_3_hit_rate,
        }


def evaluate(samples: list[BacktestSample]) -> BacktestMetrics:
    if not samples:
        return BacktestMetrics(0, 0, 0, 0, 0, 0)
    ll = brier = ex = rps = 0.0
    hits = 0
    for s in samples:
        ll += result_log_loss(s.matrix, s.actual_home, s.actual_away)
        brier += result_brier(s.matrix, s.actual_home, s.actual_away)
        ex += exact_score_log_score(s.matrix, s.actual_home, s.actual_away)
        rps += total_goals_rps(s.matrix, s.actual_home + s.actual_away)
        hits += 1 if top_k_hit(s.matrix, s.actual_home, s.actual_away, 3) else 0
    n = len(samples)
    return BacktestMetrics(
        n=n,
        result_log_loss=ll / n,
        result_brier=brier / n,
        exact_score_log_score=ex / n,
        total_goals_rps=rps / n,
        top_3_hit_rate=hits / n,
    )


@dataclass
class ModelComparison:
    metrics_by_model: dict[str, dict] = field(default_factory=dict)
    best_by_metric: dict[str, str] = field(default_factory=dict)


def compare_models(model_samples: dict[str, list[BacktestSample]]) -> ModelComparison:
    """Evaluate several models (e.g. {"v1": [...], "v2": [...]}) on their samples."""
    metrics = {name: evaluate(samples).as_dict() for name, samples in model_samples.items()}
    # Lower is better for every metric except top_3_hit_rate.
    best: dict[str, str] = {}
    metric_keys = ["result_log_loss", "result_brier", "exact_score_log_score",
                   "total_goals_rps", "top_3_hit_rate"]
    for key in metric_keys:
        if not metrics:
            continue
        higher_better = key == "top_3_hit_rate"
        best[key] = (max if higher_better else min)(
            metrics, key=lambda m: metrics[m][key]
        )
    return ModelComparison(metrics_by_model=metrics, best_by_metric=best)

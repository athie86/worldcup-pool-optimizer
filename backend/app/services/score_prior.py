"""
Football score priors  (spec WCPO-PRED-MODEL-V2 §9).

Provides the prior score-probability matrix ``Q`` on the full actual-score grid
(0..actual_score_max per team) that the V2 calibration tilts toward. Default is
Dixon-Coles; a bivariate-Poisson option and a neutral fallback are included.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import poisson

# Reuse the validated Dixon-Coles builder from the v1 model.
from .score_model import dixon_coles_matrix

LAMBDA_BOUNDS = (0.05, 6.50)
RHO_BOUNDS = (-0.30, 0.30)


def dc_prior(lh: float, la: float, rho: float, max_goals: int) -> np.ndarray:
    """Dixon-Coles prior matrix on the full grid (normalized)."""
    lh = float(min(LAMBDA_BOUNDS[1], max(LAMBDA_BOUNDS[0], lh)))
    la = float(min(LAMBDA_BOUNDS[1], max(LAMBDA_BOUNDS[0], la)))
    rho = float(min(RHO_BOUNDS[1], max(RHO_BOUNDS[0], rho)))
    return dixon_coles_matrix(lh, la, rho, max_goals)


def bivariate_poisson_prior(l1: float, l2: float, l3: float, max_goals: int) -> np.ndarray:
    """Bivariate Poisson with shared component l3 (positive score correlation)."""
    n = max_goals + 1
    mat = np.zeros((n, n))
    # P(X=i, Y=j) = e^{-(l1+l2+l3)} * sum_k l1^{i-k}/(i-k)! * l2^{j-k}/(j-k)! * l3^k/k!
    base = np.exp(-(l1 + l2 + l3))
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(0, min(i, j) + 1):
                s += (
                    (l1 ** (i - k)) / _fact(i - k)
                    * (l2 ** (j - k)) / _fact(j - k)
                    * (l3 ** k) / _fact(k)
                )
            mat[i, j] = base * s
    total = mat.sum()
    return mat / total if total > 0 else mat


def neutral_prior(max_goals: int, total_goals: float = 2.6, home_share: float = 0.5) -> np.ndarray:
    """Stage-neutral independent-Poisson prior used as the last-resort fallback."""
    lh = max(0.05, total_goals * home_share)
    la = max(0.05, total_goals * (1.0 - home_share))
    h = poisson.pmf(np.arange(max_goals + 1), lh)
    a = poisson.pmf(np.arange(max_goals + 1), la)
    mat = np.outer(h, a)
    return mat / mat.sum()


_FACT_CACHE = [1.0]


def _fact(n: int) -> float:
    while len(_FACT_CACHE) <= n:
        _FACT_CACHE.append(_FACT_CACHE[-1] * len(_FACT_CACHE))
    return _FACT_CACHE[n]

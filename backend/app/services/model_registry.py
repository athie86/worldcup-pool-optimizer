"""
Model registry  (spec WCPO-PRED-MODEL-V2 §14.1/§11.2).

Selects the prediction model by version and guarantees a safe execution flow:

    v2 attempt → (on failure/invalid) v1 attempt → (on failure) neutral fallback

so a single match can never abort a model run.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .score_model import (
    CalibratedModelResult,
    MarketProbabilities,
    fit_score_model,
    SCORE_GRID,
)
from .market_score_model_v2 import fit_market_score_model_v2, MODEL_TYPE as V2_TYPE
from .fundamental_prior import FundamentalInputs
from .odds_normalization import BookmakerMarket
from ..core.logging import logger


def _neutral_fallback(actual_score_max: int = 12) -> CalibratedModelResult:
    n = actual_score_max + 1
    mat = np.full((n, n), 1.0 / (n * n))
    diag = {
        "model_type": "neutral_fallback",
        "model_version": "fallback",
        "fit_tier": "T6_neutral_fallback",
        "warnings": ["Neutral fallback: no usable model output."],
        "market_targets": {},
        "fitted_probabilities": {},
        "prior_probabilities": {},
        "rmse": 999.0,
        "errors": ["model fit failed; neutral fallback used"],
    }
    return CalibratedModelResult(
        model_type="neutral_fallback",
        score_matrix=mat, prior_matrix=mat,
        lambda_home=1.3, lambda_away=1.3, rho=0.0,
        fit_status="incomplete_no_market_data",
        loss=999.0, converged=False,
        fitted_home_win=0.0, fitted_draw=0.0, fitted_away_win=0.0,
        prior_error=999.0, calibrated_error=999.0,
        max_single_market_error=999.0, kl_divergence=0.0, tail_mass=0.0,
        diagnostics=diag,
        model_version="fallback", fit_tier="T6_neutral_fallback",
        actual_score_max=actual_score_max, candidate_score_max=5,
        used_markets=[], missing_markets=[],
        warnings=diag["warnings"],
    )


def _is_valid(result: CalibratedModelResult) -> bool:
    try:
        mat = np.asarray(result.score_matrix, dtype=float)
        if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
            return False
        if not np.all(np.isfinite(mat)) or (mat < 0).any():
            return False
        if abs(mat.sum() - 1.0) > 1e-6:
            return False
        return True
    except Exception:
        return False


def fit(
    model_version: str,
    market: MarketProbabilities,
    bookmaker_markets: Optional[list[BookmakerMarket]] = None,
    *,
    fundamental_inputs: Optional[FundamentalInputs] = None,
    actual_score_max: int = 12,
    candidate_score_max: int = 5,
    devig_method: str = "auto",
    default_auto_devig: str = "power",
    enable_fundamental: bool = True,
    enable_asian_lines: bool = True,
    v1_fallback_enabled: bool = True,
) -> CalibratedModelResult:
    """Fit using the requested model version with automatic safe fallback."""
    version = (model_version or "v1").lower()

    if version == "v2":
        try:
            result = fit_market_score_model_v2(
                market, bookmaker_markets,
                fundamental_inputs=fundamental_inputs,
                actual_score_max=actual_score_max,
                candidate_score_max=candidate_score_max,
                devig_method=devig_method,
                default_auto_devig=default_auto_devig,
                enable_fundamental=enable_fundamental,
                enable_asian_lines=enable_asian_lines,
            )
            if _is_valid(result):
                return result
            logger.warning("model_registry: v2 produced invalid matrix; falling back")
        except Exception as exc:
            logger.error("model_registry: v2 fit failed", error=str(exc))

        if not v1_fallback_enabled:
            return _neutral_fallback(actual_score_max)

    # v1 path (default, or v2 fallback)
    try:
        result = fit_score_model(market)
        if _is_valid(result):
            return result
        logger.warning("model_registry: v1 produced invalid matrix; neutral fallback")
    except Exception as exc:
        logger.error("model_registry: v1 fit failed", error=str(exc))

    return _neutral_fallback(actual_score_max)

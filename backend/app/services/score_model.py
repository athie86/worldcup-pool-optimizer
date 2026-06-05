"""
Dixon-Coles prior + entropy-regularized market-calibrated score model.

Production pipeline:
  market odds (handled upstream)
  → normalized market probabilities (MarketProbabilities)
  → Dixon-Coles prior fitting  (λ_h, λ_a, ρ)
  → DC prior matrix, truncated to 6×6 and normalized
  → entropy-regularized calibration  (logit-softmax, 36 params)
  → final 6×6 score matrix  ← optimizer uses this
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize, brentq
from scipy.stats import poisson
from dataclasses import dataclass, field
from typing import Optional

# Re-export so existing imports of MarketProbabilities keep working.
from .poisson_model import MarketProbabilities

# ── Constants ─────────────────────────────────────────────────────────────────

CANDIDATE_MAX: int = 5       # Predictions capped at 0-5 goals
SCORE_GRID: int = 6          # CANDIDATE_MAX + 1; final matrix is SCORE_GRID × SCORE_GRID
FIT_GRID_MAX: int = 12       # Larger grid used *only* during DC parameter fitting

TAIL_MASS_WARNING_THRESHOLD: float = 0.025   # 2.5 %

ENTROPY_ALPHA: float = 250.0                 # Weight: market-fit penalty vs KL regularisation

# Used for both DC fitting and entropy calibration
MARKET_WEIGHTS: dict[str, float] = {
    "home_win":  1.25,
    "draw":      1.25,
    "away_win":  1.25,
    "over_1_5":  1.00,
    "under_1_5": 1.00,
    "over_2_5":  1.50,
    "under_2_5": 1.50,
    "over_3_5":  1.00,
    "under_3_5": 1.00,
}

RHO_BOUNDS: tuple[float, float] = (-0.30, 0.30)
LAMBDA_BOUNDS: tuple[float, float] = (0.05, 5.00)
RHO_BOUNDARY_TOL: float = 0.01


# ── Matrix utility functions ───────────────────────────────────────────────────

def matrix_market_probs(mat: np.ndarray) -> dict[str, float]:
    """Derive 1X2 and O/U probabilities from an N×N score-probability matrix."""
    n = mat.shape[0]
    rows, cols = np.indices((n, n))
    totals = rows + cols

    home_win = float(mat[rows > cols].sum())
    draw     = float(np.trace(mat))
    away_win = float(mat[rows < cols].sum())

    result: dict[str, float] = {
        "home_win": home_win,
        "draw":     draw,
        "away_win": away_win,
    }
    for line in (1.5, 2.5, 3.5):
        # e.g. "over_2_5"
        key_o = f"over_{line:.1f}".replace(".", "_")
        key_u = f"under_{line:.1f}".replace(".", "_")
        result[key_o] = float(mat[totals > line].sum())
        result[key_u] = float(mat[totals < line].sum())

    return result


def _build_targets(market: MarketProbabilities) -> dict[str, float]:
    """Flatten available MarketProbabilities to a plain dict."""
    targets: dict[str, float] = {}
    for attr in (
        "home_win", "draw", "away_win",
        "over_1_5", "under_1_5",
        "over_2_5", "under_2_5",
        "over_3_5", "under_3_5",
    ):
        val = getattr(market, attr, None)
        if val is not None:
            targets[attr] = float(val)
    return targets


def _weighted_mse(model_probs: dict[str, float], targets: dict[str, float]) -> float:
    total_w = total_e = 0.0
    for key, target in targets.items():
        w = MARKET_WEIGHTS.get(key, 1.0)
        total_e += w * (model_probs.get(key, 0.0) - target) ** 2
        total_w += w
    return total_e / total_w if total_w > 0 else 0.0


def _rmse(model_probs: dict[str, float], targets: dict[str, float]) -> float:
    errs = [(model_probs.get(k, 0.0) - v) ** 2 for k, v in targets.items()]
    return float(np.sqrt(np.mean(errs))) if errs else 0.0


# ── Dixon-Coles matrix builder ────────────────────────────────────────────────

def _dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles τ correction—applied only to low-score cells."""
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_matrix(lh: float, la: float, rho: float, max_goals: int) -> np.ndarray:
    """
    Build a normalized Dixon-Coles score matrix up to *max_goals* per team.

    Starts from independent Poisson, applies τ correction to the
    {0,1}×{0,1} cells, clamps negatives, then normalizes to sum=1.
    """
    h_pmf = poisson.pmf(np.arange(max_goals + 1), lh)
    a_pmf = poisson.pmf(np.arange(max_goals + 1), la)
    mat = np.outer(h_pmf, a_pmf)

    for i in range(min(2, max_goals + 1)):
        for j in range(min(2, max_goals + 1)):
            mat[i, j] = max(0.0, mat[i, j] * _dc_tau(i, j, lh, la, rho))

    total = mat.sum()
    if total > 1e-12:
        mat /= total
    return mat


# ── DC parameter fitting ───────────────────────────────────────────────────────

@dataclass
class _DCFit:
    lh: float
    la: float
    rho: float
    converged: bool
    loss: float
    rho_hit_boundary: bool = False


def _initial_lambdas(market: MarketProbabilities) -> tuple[float, float]:
    """Rough initial (λ_h, λ_a) from O/U 2.5 + 1X2 share."""
    lambda_total = 2.5
    if market.over_2_5 is not None:
        try:
            def f(lam: float) -> float:
                return float(sum(poisson.pmf(k, lam) for k in range(3, 20))) - market.over_2_5
            lambda_total = brentq(f, 0.1, 15.0)
        except Exception:
            pass

    hw = market.home_win or 0.45
    dw = market.draw    or 0.25
    aw = market.away_win or 0.30

    home_share = (hw + 0.5 * dw) / (hw + dw + aw) if (hw + dw + aw) > 0 else 0.55
    lh0 = max(0.1, min(4.9, lambda_total * home_share))
    la0 = max(0.1, min(4.9, lambda_total * (1.0 - home_share)))
    return lh0, la0


def _fit_dc_params(market: MarketProbabilities) -> _DCFit:
    """Minimise weighted MSE between DC-matrix-implied and market probabilities."""
    targets = _build_targets(market)

    def objective(params: np.ndarray) -> float:
        lh, la, rho = float(params[0]), float(params[1]), float(params[2])
        try:
            mat = dixon_coles_matrix(lh, la, rho, FIT_GRID_MAX)
            return _weighted_mse(matrix_market_probs(mat), targets)
        except Exception:
            return 1e6

    lh0, la0 = _initial_lambdas(market)
    starts = [
        (lh0, la0, 0.00),
        (1.35, 1.10, 0.00),
        (1.50, 1.00, 0.00),
        (1.00, 1.50, 0.00),
        (2.00, 0.75, -0.10),
        (0.75, 2.00, 0.00),
        (1.35, 1.10, -0.10),
    ]
    bounds = [LAMBDA_BOUNDS, LAMBDA_BOUNDS, RHO_BOUNDS]
    best = None

    for start in starts:
        try:
            res = minimize(
                objective, start, method="L-BFGS-B", bounds=bounds,
                options={"ftol": 1e-10, "gtol": 1e-8, "maxiter": 1000},
            )
            if best is None or res.fun < best.fun:
                best = res
        except Exception:
            continue

    if best is None:
        return _DCFit(lh=1.35, la=1.10, rho=0.0, converged=False, loss=999.0)

    lh_f, la_f, rho_f = float(best.x[0]), float(best.x[1]), float(best.x[2])
    rho_hit = (
        abs(rho_f - RHO_BOUNDS[1]) < RHO_BOUNDARY_TOL
        or abs(rho_f - RHO_BOUNDS[0]) < RHO_BOUNDARY_TOL
    )
    return _DCFit(
        lh=lh_f, la=la_f, rho=rho_f,
        converged=bool(best.success),
        loss=float(best.fun),
        rho_hit_boundary=rho_hit,
    )


# ── Entropy-regularized calibration ───────────────────────────────────────────

@dataclass
class _CalibResult:
    matrix: np.ndarray
    converged: bool
    kl_divergence: float
    calibrated_error: float
    max_single_market_error: float
    calibrated_probs: dict[str, float]


def _entropy_calibrate(
    Q: np.ndarray,
    market: MarketProbabilities,
    alpha: float = ENTROPY_ALPHA,
) -> _CalibResult:
    """
    Solve:  min_{P}  KL(P || Q)  +  α · weighted_mse(P, market_targets)
            s.t. P ≥ 0, Σ P = 1

    Parameterisation: P = softmax(z),  z ∈ R^{SCORE_GRID²}.
    KL(P||Q) is the forward KL, which pulls P toward Q.
    """
    targets = _build_targets(market)
    eps = 1e-12

    Q_safe = np.maximum(Q, eps).copy()
    Q_safe /= Q_safe.sum()
    log_Q = np.log(Q_safe).flatten()

    z0 = log_Q.copy()

    def softmax_mat(z: np.ndarray) -> np.ndarray:
        z2 = z.reshape(SCORE_GRID, SCORE_GRID)
        z2 = z2 - z2.max()
        e = np.exp(z2)
        return e / e.sum()

    def kl_forward(P_flat: np.ndarray) -> float:
        mask = P_flat > eps
        return float(np.sum(P_flat[mask] * (np.log(P_flat[mask]) - log_Q[mask])))

    def objective(z: np.ndarray) -> float:
        P = softmax_mat(z)
        kl = kl_forward(P.flatten())
        mse = _weighted_mse(matrix_market_probs(P), targets)
        return kl + alpha * mse

    try:
        res = minimize(
            objective, z0, method="L-BFGS-B",
            options={"ftol": 1e-10, "gtol": 1e-8, "maxiter": 2000},
        )
        P = softmax_mat(res.x)
        converged = bool(res.success)
    except Exception:
        P = Q_safe.copy()
        converged = False

    calib_probs = matrix_market_probs(P)
    rmse = _rmse(calib_probs, targets)
    max_err = (
        max(abs(calib_probs.get(k, 0.0) - v) for k, v in targets.items())
        if targets else 0.0
    )
    kl_div = kl_forward(P.flatten())

    return _CalibResult(
        matrix=P,
        converged=converged,
        kl_divergence=kl_div,
        calibrated_error=rmse,
        max_single_market_error=max_err,
        calibrated_probs=calib_probs,
    )


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class CalibratedModelResult:
    model_type: str
    score_matrix: np.ndarray       # 6×6 — final production matrix (calibrated)
    prior_matrix: np.ndarray       # 6×6 — DC prior (normalized)

    lambda_home: float
    lambda_away: float
    rho: float

    fit_status: str
    loss: float                    # DC fitting weighted MSE (kept for DB compat)
    converged: bool

    # Kept for backward compat with model_runs.py DB writes
    fitted_home_win: float
    fitted_draw: float
    fitted_away_win: float

    # Rich diagnostics
    prior_error: float             # RMSE: DC prior vs market
    calibrated_error: float        # RMSE: calibrated matrix vs market
    max_single_market_error: float
    kl_divergence: float
    tail_mass: float               # probability mass above score-grid before normalization

    diagnostics: dict              # stored as JSONB in DB


# ── Fit-status classification ──────────────────────────────────────────────────

def _classify_fit(rmse: float, h2h_only: bool, any_converged: bool) -> str:
    if not any_converged:
        return "weak"
    if h2h_only:
        return "weak"
    if rmse <= 0.02:
        return "good"
    if rmse <= 0.04:
        return "acceptable"
    return "weak"


# ── Fallback helpers ───────────────────────────────────────────────────────────

def _poisson_6x6(lh: float, la: float) -> tuple[np.ndarray, float]:
    """Independent Poisson 6×6 matrix + tail mass before normalization."""
    large = np.outer(
        poisson.pmf(np.arange(FIT_GRID_MAX + 1), lh),
        poisson.pmf(np.arange(FIT_GRID_MAX + 1), la),
    )
    raw6 = large[:SCORE_GRID, :SCORE_GRID].copy()
    tail = float(1.0 - raw6.sum())
    return raw6 / raw6.sum(), tail


def _fallback_poisson_result(
    market: MarketProbabilities,
    warnings: list[str],
) -> CalibratedModelResult:
    lh0, la0 = _initial_lambdas(market)
    mat6, tail = _poisson_6x6(lh0, la0)
    probs = matrix_market_probs(mat6)
    targets = _build_targets(market)
    rmse = _rmse(probs, targets)

    diag: dict = {
        "model_type": "independent_poisson_fallback",
        "market_targets": targets,
        "fitted_probabilities": probs,
        "prior_probabilities": probs,
        "rmse": rmse,
        "prior_rmse": rmse,
        "max_single_market_error": 0.0,
        "kl_divergence_from_prior": 0.0,
        "tail_mass_before_normalization": tail,
        "rho": 0.0,
        "dc_converged": False,
        "entropy_calibration_converged": False,
        "rho_hit_boundary": False,
        "h2h_only": market.over_2_5 is None,
        "warnings": warnings + ["Using independent Poisson fallback."],
    }
    return CalibratedModelResult(
        model_type="independent_poisson_fallback",
        score_matrix=mat6,
        prior_matrix=mat6,
        lambda_home=lh0, lambda_away=la0, rho=0.0,
        fit_status="weak",
        loss=rmse, converged=False,
        fitted_home_win=probs.get("home_win", 0.0),
        fitted_draw=probs.get("draw", 0.0),
        fitted_away_win=probs.get("away_win", 0.0),
        prior_error=rmse, calibrated_error=rmse,
        max_single_market_error=0.0, kl_divergence=0.0, tail_mass=tail,
        diagnostics=diag,
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def fit_score_model(market: MarketProbabilities) -> CalibratedModelResult:
    """
    Fit the full calibration pipeline for one match.

    Fallback order:
      entropy-calibrated Dixon-Coles
      → DC only (entropy calibration rejected)
      → independent Poisson (DC fitting failed)
      → incomplete  (h2h missing)
    """
    warnings: list[str] = []

    # ── 0. Guard: h2h required ──────────────────────────────────────────── #
    if market.home_win is None or market.draw is None or market.away_win is None:
        dummy = np.full(
            (SCORE_GRID, SCORE_GRID), 1.0 / (SCORE_GRID * SCORE_GRID)
        )
        return CalibratedModelResult(
            model_type="incomplete_missing_h2h",
            score_matrix=dummy, prior_matrix=dummy,
            lambda_home=1.35, lambda_away=1.10, rho=0.0,
            fit_status="incomplete_missing_h2h",
            loss=999.0, converged=False,
            fitted_home_win=0.0, fitted_draw=0.0, fitted_away_win=0.0,
            prior_error=999.0, calibrated_error=999.0,
            max_single_market_error=999.0, kl_divergence=0.0, tail_mass=0.0,
            diagnostics={
                "error": "Missing h2h market",
                "warnings": ["Missing h2h market"],
                "model_type": "incomplete_missing_h2h",
            },
        )

    targets = _build_targets(market)
    h2h_only = not any(k.startswith("over") for k in targets)
    if h2h_only:
        warnings.append("Totals market missing. Model calibrated only to 1X2.")

    # ── 1. Fit Dixon-Coles parameters ───────────────────────────────────── #
    try:
        dc = _fit_dc_params(market)
    except Exception as exc:
        warnings.append(f"Dixon-Coles fitting failed: {exc}. Using independent Poisson.")
        return _fallback_poisson_result(market, warnings)

    if not dc.converged:
        warnings.append("Dixon-Coles fitting did not converge cleanly.")
    if dc.rho_hit_boundary:
        warnings.append(
            f"ρ hit the fitting boundary ({dc.rho:+.3f}). "
            "DC low-score correction may be unreliable."
        )

    # ── 2. DC prior matrix → truncate to 6×6 → normalize ───────────────── #
    try:
        dc_large = dixon_coles_matrix(dc.lh, dc.la, dc.rho, FIT_GRID_MAX)
        dc_6x6_raw = dc_large[:SCORE_GRID, :SCORE_GRID].copy()
        tail_mass = float(1.0 - dc_6x6_raw.sum())

        if tail_mass > TAIL_MASS_WARNING_THRESHOLD:
            warnings.append(
                f"High tail mass ({tail_mass:.1%}): "
                "score grid may be too narrow for this match."
            )

        dc_6x6 = dc_6x6_raw / dc_6x6_raw.sum()
    except Exception as exc:
        warnings.append(f"DC matrix generation failed: {exc}. Using independent Poisson.")
        return _fallback_poisson_result(market, warnings)

    prior_probs = matrix_market_probs(dc_6x6)
    prior_error = _rmse(prior_probs, targets)

    # ── 3. Entropy-regularized calibration ─────────────────────────────── #
    try:
        calib = _entropy_calibrate(dc_6x6, market)

        # Reject calibration if it materially worsened fit (with a small slack)
        if calib.calibrated_error > prior_error * 1.5 + 0.005:
            warnings.append(
                "Entropy calibration increased market error; "
                "reverting to DC prior matrix."
            )
            final_matrix    = dc_6x6
            entropy_ok      = False
            cal_error       = prior_error
            max_err         = max(
                abs(prior_probs.get(k, 0.0) - v) for k, v in targets.items()
            ) if targets else 0.0
            kl_div          = 0.0
            cal_probs       = prior_probs
        else:
            final_matrix    = calib.matrix
            entropy_ok      = calib.converged
            cal_error       = calib.calibrated_error
            max_err         = calib.max_single_market_error
            kl_div          = calib.kl_divergence
            cal_probs       = calib.calibrated_probs

        if not entropy_ok:
            warnings.append("Entropy calibration did not converge cleanly.")

    except Exception as exc:
        warnings.append(f"Entropy calibration failed: {exc}. Using DC prior matrix.")
        final_matrix = dc_6x6
        entropy_ok   = False
        cal_error    = prior_error
        max_err      = max(
            abs(prior_probs.get(k, 0.0) - v) for k, v in targets.items()
        ) if targets else 0.0
        kl_div       = 0.0
        cal_probs    = prior_probs

    fit_status = _classify_fit(cal_error, h2h_only, dc.converged or entropy_ok)

    # ── 4. Build rich diagnostics dict ─────────────────────────────────── #
    diagnostics: dict = {
        "model_type":                        "entropy_calibrated_dixon_coles",
        "market_targets":                    targets,
        "fitted_probabilities":              cal_probs,
        "prior_probabilities":               prior_probs,
        "rmse":                              cal_error,
        "prior_rmse":                        prior_error,
        "max_single_market_error":           max_err,
        "kl_divergence_from_prior":          kl_div,
        "tail_mass_before_normalization":    tail_mass,
        "rho":                               dc.rho,
        "dc_converged":                      dc.converged,
        "entropy_calibration_converged":     entropy_ok,
        "rho_hit_boundary":                  dc.rho_hit_boundary,
        "h2h_only":                          h2h_only,
        "warnings":                          warnings,
        # Legacy keys kept for existing diagnostics endpoint
        "fit_max_goals":                     SCORE_GRID - 1,
    }

    return CalibratedModelResult(
        model_type="entropy_calibrated_dixon_coles",
        score_matrix=final_matrix,
        prior_matrix=dc_6x6,
        lambda_home=dc.lh,
        lambda_away=dc.la,
        rho=dc.rho,
        fit_status=fit_status,
        loss=float(dc.loss),
        converged=dc.converged,
        fitted_home_win=float(cal_probs.get("home_win", 0.0)),
        fitted_draw=float(cal_probs.get("draw", 0.0)),
        fitted_away_win=float(cal_probs.get("away_win", 0.0)),
        prior_error=prior_error,
        calibrated_error=cal_error,
        max_single_market_error=max_err,
        kl_divergence=kl_div,
        tail_mass=tail_mass,
        diagnostics=diagnostics,
    )


# ── Convenience re-export (legacy call-sites that imported fit_poisson) ───────

def fit_poisson(market: MarketProbabilities) -> CalibratedModelResult:
    """Backward-compat shim — delegates to fit_score_model."""
    return fit_score_model(market)

import numpy as np
from scipy.optimize import minimize, brentq
from scipy.stats import poisson
from dataclasses import dataclass
from typing import Optional


@dataclass
class MarketProbabilities:
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    over_1_5: Optional[float] = None
    under_1_5: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    over_3_5: Optional[float] = None
    under_3_5: Optional[float] = None


@dataclass
class FitResult:
    lambda_home: float
    lambda_away: float
    loss: float
    converged: bool
    fit_status: str  # good, acceptable, weak, incomplete, fit_failed
    score_matrix: np.ndarray  # shape (fit_max+1, fit_max+1)
    fitted_home_win: float
    fitted_draw: float
    fitted_away_win: float
    diagnostics: dict


FIT_MAX_GOALS = 12
CANDIDATE_MAX = 5
LAMBDA_BOUNDS = (0.05, 6.00)
FALLBACK_BOUNDS = (0.01, 8.00)

WEIGHTS = {
    "home_win": 1.00,
    "draw": 1.25,
    "away_win": 1.00,
    "over_1_5": 0.75,
    "under_1_5": 0.75,
    "over_2_5": 1.00,
    "under_2_5": 1.00,
    "over_3_5": 0.75,
    "under_3_5": 0.75,
}


def compute_score_matrix(lh: float, la: float, max_goals: int) -> np.ndarray:
    """Return (max_goals+1, max_goals+1) matrix of P(H=h, A=a)."""
    h_probs = poisson.pmf(np.arange(max_goals + 1), lh)
    a_probs = poisson.pmf(np.arange(max_goals + 1), la)
    return np.outer(h_probs, a_probs)


def model_probabilities(lh: float, la: float, max_goals: int) -> dict:
    """Compute model-implied 1X2 and O/U probabilities."""
    mat = compute_score_matrix(lh, la, max_goals)
    n = max_goals + 1

    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for h in range(n):
        for a in range(n):
            p = mat[h, a]
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    totals = {}
    for line in [1.5, 2.5, 3.5]:
        over = 0.0
        under = 0.0
        for h in range(n):
            for a in range(n):
                p = mat[h, a]
                if h + a > line:
                    over += p
                elif h + a < line:
                    under += p
        totals[line] = (over, under)

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "over_1_5": totals[1.5][0],
        "under_1_5": totals[1.5][1],
        "over_2_5": totals[2.5][0],
        "under_2_5": totals[2.5][1],
        "over_3_5": totals[3.5][0],
        "under_3_5": totals[3.5][1],
    }


def tail_mass(lh: float, la: float, max_goals: int) -> float:
    mat = compute_score_matrix(lh, la, max_goals)
    return float(1.0 - mat.sum())


def fit_poisson(market: MarketProbabilities) -> FitResult:
    """Fit Poisson model to market probabilities."""
    if market.home_win is None or market.draw is None or market.away_win is None:
        return FitResult(
            lambda_home=1.5, lambda_away=1.0, loss=999.0, converged=False,
            fit_status="incomplete_missing_h2h",
            score_matrix=compute_score_matrix(1.5, 1.0, FIT_MAX_GOALS),
            fitted_home_win=0.0, fitted_draw=0.0, fitted_away_win=0.0,
            diagnostics={"error": "Missing h2h market"}
        )

    fit_max = FIT_MAX_GOALS

    # Build targets dict
    targets = {
        "home_win": market.home_win,
        "draw": market.draw,
        "away_win": market.away_win,
    }
    if market.over_1_5 is not None:
        targets["over_1_5"] = market.over_1_5
        targets["under_1_5"] = market.under_1_5
    if market.over_2_5 is not None:
        targets["over_2_5"] = market.over_2_5
        targets["under_2_5"] = market.under_2_5
    if market.over_3_5 is not None:
        targets["over_3_5"] = market.over_3_5
        targets["under_3_5"] = market.under_3_5

    h2h_only = not any(k.startswith("over") for k in targets)

    def objective(params):
        lh, la = params
        if lh <= 0 or la <= 0:
            return 1e6
        model = model_probabilities(lh, la, fit_max)
        loss = 0.0
        for key, target in targets.items():
            w = WEIGHTS.get(key, 1.0)
            loss += w * (model[key] - target) ** 2
        return loss

    # Initial guess
    if market.over_2_5 is not None:
        lambda_total = 2.5
        try:
            def f(lam):
                return sum(poisson.pmf(k, lam) for k in range(3, 20)) - market.over_2_5
            try:
                lambda_total = brentq(f, 0.1, 15.0)
            except Exception:
                lambda_total = 2.5
        except Exception:
            pass
    else:
        lambda_total = 2.5

    home_raw = market.home_win + 0.5 * market.draw
    away_raw = market.away_win + 0.5 * market.draw
    total = home_raw + away_raw
    home_share = home_raw / total if total > 0 else 0.5

    lh0 = lambda_total * home_share
    la0 = lambda_total * (1 - home_share)
    lh0 = max(0.1, min(5.9, lh0))
    la0 = max(0.1, min(5.9, la0))

    starts = [
        (lh0, la0),
        (1.0, 1.0),
        (1.5, 1.0),
        (1.0, 1.5),
        (2.0, 0.75),
        (0.75, 2.0),
        (2.0, 2.0),
    ]

    bounds = [LAMBDA_BOUNDS, LAMBDA_BOUNDS]
    best_result = None

    for start in starts:
        try:
            res = minimize(
                objective,
                start,
                method="L-BFGS-B",
                bounds=bounds,
                options={"ftol": 1e-10, "gtol": 1e-8, "maxiter": 1000}
            )
            if best_result is None or res.fun < best_result.fun:
                best_result = res
        except Exception:
            continue

    # Fallback with broader bounds
    if best_result is None or not best_result.success:
        fallback_bounds = [FALLBACK_BOUNDS, FALLBACK_BOUNDS]
        for start in starts:
            try:
                res = minimize(
                    objective, start, method="L-BFGS-B",
                    bounds=fallback_bounds,
                    options={"ftol": 1e-10, "gtol": 1e-8, "maxiter": 1000}
                )
                if best_result is None or res.fun < best_result.fun:
                    best_result = res
            except Exception:
                continue

    if best_result is None:
        return FitResult(
            lambda_home=1.5, lambda_away=1.0, loss=999.0, converged=False,
            fit_status="fit_failed",
            score_matrix=compute_score_matrix(1.5, 1.0, fit_max),
            fitted_home_win=0.0, fitted_draw=0.0, fitted_away_win=0.0,
            diagnostics={"error": "Optimization failed"}
        )

    lh_fit, la_fit = best_result.x
    loss = float(best_result.fun)

    # Check tail mass
    tm = tail_mass(lh_fit, la_fit, fit_max)
    if tm > 0.001:
        fit_max = max(fit_max, 15)

    score_mat = compute_score_matrix(lh_fit, la_fit, fit_max)
    fitted_probs = model_probabilities(lh_fit, la_fit, fit_max)

    # Compute RMSE
    errors = []
    for key, target in targets.items():
        errors.append((fitted_probs[key] - target) ** 2)
    rmse = float(np.sqrt(np.mean(errors))) if errors else 0.0

    # Determine fit status
    if h2h_only:
        fit_status = "weak"
    elif rmse <= 0.02:
        fit_status = "good"
    elif rmse <= 0.04:
        fit_status = "acceptable"
    else:
        fit_status = "weak"

    diagnostics = {
        "rmse": rmse,
        "h2h_only": h2h_only,
        "tail_mass": tm,
        "fit_max_goals": fit_max,
        "market_targets": targets,
        "fitted_probabilities": fitted_probs,
        "warnings": [],
    }
    if h2h_only:
        diagnostics["warnings"].append("totals_missing_fit_less_stable")
    if tm > 0.001:
        diagnostics["warnings"].append(f"high_tail_mass_{tm:.4f}")
    if rmse > 0.04:
        diagnostics["warnings"].append("poor_market_fit")

    return FitResult(
        lambda_home=float(lh_fit),
        lambda_away=float(la_fit),
        loss=loss,
        converged=bool(best_result.success),
        fit_status=fit_status,
        score_matrix=score_mat,
        fitted_home_win=fitted_probs["home_win"],
        fitted_draw=fitted_probs["draw"],
        fitted_away_win=fitted_probs["away_win"],
        diagnostics=diagnostics,
    )

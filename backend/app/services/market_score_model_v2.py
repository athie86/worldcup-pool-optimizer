"""
Market score model V2  (spec WCPO-PRED-MODEL-V2 §4/§9/§10/§11).

Pipeline for one match:

    bookmaker markets
      → canonical de-vigged consensus constraints  (market_constraints)
      → football score prior Q on the full 0..N grid (Dixon-Coles, fundamental-blended)
      → maximum-entropy exponential-tilt calibration against the constraints
      → validated full actual-score matrix P  (rejection rules → prior fallback)
      → derived expected goals / probabilities / diagnostics

Returns a ``CalibratedModelResult`` (the same dataclass the optimizer/DB use)
with the V2 fields populated and ``score_matrix`` sized to ``actual_score_max``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.optimize import minimize, brentq
from scipy.stats import poisson

from .score_model import (
    CalibratedModelResult,
    MarketProbabilities,
    matrix_market_probs,
    _fit_dc_params,
)
from .score_prior import dc_prior, neutral_prior
from .fundamental_prior import (
    FundamentalInputs,
    FundamentalPrior,
    build_fundamental_prior,
    reliability_weight,
    blend_mu,
)
from .market_constraints import (
    MarketConstraintInput,
    ConstraintBuildResult,
    build_constraints,
)
from .odds_normalization import BookmakerMarket

MODEL_VERSION = "2.0.0"
MODEL_TYPE = "market_score_model_v2"

CALIBRATION_ALPHA = 400.0
BETA_BOUNDS = (-2.5, 2.5)

XG_BOUNDS_HOME = (0.05, 6.50)
XG_BOUNDS_AWAY = (0.05, 6.50)
XG_BOUNDS_TOTAL = (0.10, 9.00)

TAIL_MASS_WARNING = 0.005
TAIL_MASS_STRONG_WARNING = 0.025


# ── constraint operators (spec §7.3) ────────────────────────────────────────


def _operator(P: np.ndarray, I: np.ndarray, J: np.ndarray,
              ctype: str, line: Optional[float]) -> float:
    T = I + J
    D = I - J
    if ctype == "result_home_win":
        return float(P[I > J].sum())
    if ctype == "result_draw":
        return float(np.trace(P))
    if ctype == "result_away_win":
        return float(P[I < J].sum())
    if ctype == "total_over_half_line":
        return float(P[T > line].sum())
    if ctype == "total_under_half_line":
        return float(P[T < line].sum())
    if ctype == "total_over_integer_line":
        over = float(P[T > line].sum())
        under = float(P[T < line].sum())
        denom = over + under
        return over / denom if denom > 1e-12 else 0.0
    if ctype == "total_under_integer_line":
        over = float(P[T > line].sum())
        under = float(P[T < line].sum())
        denom = over + under
        return under / denom if denom > 1e-12 else 0.0
    if ctype == "team_total_home_over_half_line":
        return float(P[I > line].sum())
    if ctype == "team_total_home_under_half_line":
        return float(P[I < line].sum())
    if ctype == "team_total_away_over_half_line":
        return float(P[J > line].sum())
    if ctype == "team_total_away_under_half_line":
        return float(P[J < line].sum())
    if ctype == "btts_yes":
        return float(P[(I > 0) & (J > 0)].sum())
    if ctype == "btts_no":
        return 1.0 - float(P[(I > 0) & (J > 0)].sum())
    if ctype == "draw_no_bet_home":
        hw = float(P[I > J].sum())
        aw = float(P[I < J].sum())
        denom = hw + aw
        return hw / denom if denom > 1e-12 else 0.0
    if ctype == "draw_no_bet_away":
        hw = float(P[I > J].sum())
        aw = float(P[I < J].sum())
        denom = hw + aw
        return aw / denom if denom > 1e-12 else 0.0
    if ctype == "spread_home_half_line":
        return float(P[(D + line) > 0].sum())
    if ctype == "spread_away_half_line":
        return float(P[(-D - line) > 0].sum())
    return 0.0


# ── market seed extraction ──────────────────────────────────────────────────


def _market_probs_from_constraints(constraints: list[MarketConstraintInput]) -> MarketProbabilities:
    """Build a v1-style MarketProbabilities (1X2 + 1.5/2.5/3.5 totals) for the
    Dixon-Coles seed fit, from the consensus constraint targets."""
    mp = MarketProbabilities()
    by_type: dict[str, list[tuple[float, float]]] = {}
    totals: dict[tuple[str, float], list[tuple[float, float]]] = {}
    for c in constraints:
        if c.constraint_type == "result_home_win":
            by_type.setdefault("home_win", []).append((c.target_value, c.weight))
        elif c.constraint_type == "result_draw":
            by_type.setdefault("draw", []).append((c.target_value, c.weight))
        elif c.constraint_type == "result_away_win":
            by_type.setdefault("away_win", []).append((c.target_value, c.weight))
        elif c.constraint_type in ("total_over_half_line", "total_under_half_line") and c.line is not None:
            side = "over" if "over" in c.constraint_type else "under"
            totals.setdefault((side, round(c.line, 1)), []).append((c.target_value, c.weight))

    def wavg(items):
        tw = sum(w for _, w in items)
        return sum(v * w for v, w in items) / tw if tw > 0 else None

    for k in ("home_win", "draw", "away_win"):
        if k in by_type:
            setattr(mp, k, wavg(by_type[k]))

    line_map = {1.5: ("over_1_5", "under_1_5"), 2.5: ("over_2_5", "under_2_5"),
                3.5: ("over_3_5", "under_3_5")}
    for line, (over_attr, under_attr) in line_map.items():
        ov = totals.get(("over", line))
        un = totals.get(("under", line))
        if ov:
            setattr(mp, over_attr, wavg(ov))
        if un:
            setattr(mp, under_attr, wavg(un))
    return mp


def _seed_lambdas(mp: MarketProbabilities) -> tuple[float, float]:
    lambda_total = 2.6
    over = mp.over_2_5 if mp.over_2_5 is not None else None
    if over is not None:
        try:
            def f(lam: float) -> float:
                return float(sum(poisson.pmf(k, lam) for k in range(3, 25))) - over
            lambda_total = brentq(f, 0.1, 16.0)
        except Exception:
            lambda_total = 2.6
    hw = mp.home_win or 0.4
    dw = mp.draw or 0.27
    aw = mp.away_win or 0.33
    denom = hw + dw + aw
    home_share = (hw + 0.5 * dw) / denom if denom > 0 else 0.5
    lh = max(0.1, min(6.0, lambda_total * home_share))
    la = max(0.1, min(6.0, lambda_total * (1 - home_share)))
    return lh, la


# ── fit tier classification (spec §11) ──────────────────────────────────────


def _classify_tier(coverage: dict[str, int]) -> str:
    has_result = coverage.get("result", 0) > 0
    has_total = coverage.get("total_goals", 0) > 0
    extras = sum(coverage.get(f, 0) > 0 for f in
                 ("team_goals", "both_teams_to_score", "goal_difference",
                  "result_conditional_no_draw"))
    if has_result and has_total and extras >= 1:
        return "T0_rich"
    if has_result and has_total:
        return "T1_standard"
    if has_result and extras >= 1:
        return "T2_result_plus_partial"
    if has_result:
        return "T3_result_only"
    if has_total:
        return "T4_totals_only"
    return "T5_fundamental_only"


def _fit_status_for_tier(tier: str, calibrated_error: float, has_result: bool) -> str:
    if not has_result and tier == "T4_totals_only":
        return "incomplete_missing_result_market"
    if tier in ("T5_fundamental_only", "T6_neutral_fallback"):
        return "incomplete_no_market_data"
    if tier == "T0_rich":
        return "good" if calibrated_error <= 0.02 else "acceptable"
    if tier == "T1_standard":
        if calibrated_error <= 0.02:
            return "good"
        if calibrated_error <= 0.04:
            return "acceptable"
        return "weak"
    return "weak"


# ── calibration (maximum-entropy exponential tilt) ──────────────────────────


def _build_features(I: np.ndarray, J: np.ndarray) -> list[np.ndarray]:
    """Compact, well-conditioned tilt basis (spec §10.1)."""
    return [
        I.astype(float),                       # home goals mean
        J.astype(float),                       # away goals mean
        (I > J).astype(float),                 # home-win mass
        (I == J).astype(float),                # draw mass
        ((I > 0) & (J > 0)).astype(float),     # both-teams-to-score mass
    ]


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(1 - eps, max(eps, p))
    return float(np.log(p / (1 - p)))


def _constraint_loss(P, I, J, constraints) -> tuple[float, float, float]:
    """Return (weighted_mean_sq_logit_error, total_weight, max_abs_error)."""
    total_w = 0.0
    total_e = 0.0
    max_err = 0.0
    for c in constraints:
        model_val = _operator(P, I, J, c.constraint_type, c.line)
        err = abs(model_val - c.target_value)
        max_err = max(max_err, err)
        diff = _logit(model_val) - _logit(c.target_value)
        total_e += c.weight * diff * diff
        total_w += c.weight
    if total_w <= 0:
        return 0.0, 0.0, 0.0
    return total_e / total_w, total_w, max_err


def _calibrate(Q: np.ndarray, constraints, I, J,
               alpha: float = CALIBRATION_ALPHA):
    features = _build_features(I, J)
    log_Q = np.log(np.maximum(Q, 1e-300))

    def make_P(beta):
        logits = np.zeros_like(Q)
        for b, F in zip(beta, features):
            logits = logits + b * F
        logits = logits + log_Q
        logits -= logits.max()
        M = np.exp(logits)
        s = M.sum()
        return M / s if s > 0 else Q

    def objective(beta):
        P = make_P(beta)
        loss, _, _ = _constraint_loss(P, I, J, constraints)
        mask = P > 1e-300
        kl = float(np.sum(P[mask] * (np.log(P[mask]) - log_Q[mask])))
        return kl + alpha * loss

    beta0 = np.zeros(len(features))
    bounds = [BETA_BOUNDS] * len(features)
    try:
        res = minimize(objective, beta0, method="L-BFGS-B", bounds=bounds,
                       options={"ftol": 1e-10, "gtol": 1e-8, "maxiter": 2000})
        P = make_P(res.x)
        converged = bool(res.success)
        beta = res.x
    except Exception:
        P = Q.copy()
        converged = False
        beta = beta0

    loss, _, max_err = _constraint_loss(P, I, J, constraints)
    mask = P > 1e-300
    kl = float(np.sum(P[mask] * (np.log(P[mask]) - log_Q[mask])))
    rmse = float(np.sqrt(loss)) if loss > 0 else 0.0
    return P, converged, kl, rmse, max_err, {f"beta_{i}": float(b) for i, b in enumerate(beta)}


# ── derived quantities ──────────────────────────────────────────────────────


def _expected_goals(P, I, J) -> tuple[float, float]:
    return float((P * I).sum()), float((P * J).sum())


def _build_result(P, Q, constraints, build: ConstraintBuildResult, tier, fit_status,
                  lh_seed, la_seed, rho, prior_error, cal_error, kl, max_err,
                  calib_converged, candidate_score_max, actual_score_max,
                  tail_mass, reliability, warnings, calib_params,
                  fundamental: Optional[FundamentalPrior]) -> CalibratedModelResult:
    I, J = np.indices(P.shape)
    home_xg, away_xg = _expected_goals(P, I, J)
    probs = matrix_market_probs(P)
    prior_probs = matrix_market_probs(Q)
    market_targets = _market_probs_to_dict(_market_probs_from_constraints(constraints))

    constraint_details = []
    for c in constraints:
        fitted = _operator(P, I, J, c.constraint_type, c.line)
        constraint_details.append({
            "market_key": c.market_key,
            "market_family": c.market_family,
            "constraint_type": c.constraint_type,
            "side": c.side,
            "line": c.line,
            "target_value": c.target_value,
            "fitted_value": fitted,
            "error": fitted - c.target_value,
            "weight": c.weight,
            "bookmaker_count": c.bookmaker_count,
            "quality_label": c.quality_label,
            "devig_method": c.devig_method,
        })

    diagnostics = {
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "fit_tier": tier,
        "fit_status": fit_status,
        "scoring_basis": "regular_time_90",
        "actual_score_max": actual_score_max,
        "candidate_score_max": candidate_score_max,
        "used_markets": build.used_markets,
        "missing_markets": build.missing_markets,
        "market_coverage_score": build.market_coverage_score,
        "market_reliability_weight": reliability,
        "constraints": {
            "count": len(constraints),
            "by_family": build.coverage_by_family,
            "max_error": max_err,
            "rmse": cal_error,
        },
        "constraint_details": constraint_details,
        "prior": {
            "type": "dixon_coles",
            "lambda_home": lh_seed,
            "lambda_away": la_seed,
            "rho": rho,
            "home_xg": float((Q * I).sum()),
            "away_xg": float((Q * J).sum()),
            "error": prior_error,
        },
        "calibration": {
            "type": "maximum_entropy_exponential_tilt",
            "converged": calib_converged,
            "kl_divergence": kl,
            "regularization_alpha": CALIBRATION_ALPHA,
            "parameters": calib_params,
            "error": cal_error,
        },
        "final": {
            "home_xg": home_xg,
            "away_xg": away_xg,
            "total_xg": home_xg + away_xg,
            "home_win": probs.get("home_win", 0.0),
            "draw": probs.get("draw", 0.0),
            "away_win": probs.get("away_win", 0.0),
            "btts_yes": float(P[(I > 0) & (J > 0)].sum()),
            "tail_mass": tail_mass,
        },
        "fundamental": (fundamental.diagnostics | {"mu_home": fundamental.mu_home,
                        "mu_away": fundamental.mu_away, "source": fundamental.source})
                        if fundamental else None,
        # ── keys consumed by the existing diagnostics endpoint ──────────────
        "market_targets": market_targets,
        "fitted_probabilities": probs,
        "prior_probabilities": prior_probs,
        "rmse": cal_error,
        "prior_rmse": prior_error,
        "max_single_market_error": max_err,
        "kl_divergence_from_prior": kl,
        "tail_mass_before_normalization": tail_mass,
        "rho": rho,
        "warnings": warnings,
        "errors": [],
    }

    return CalibratedModelResult(
        model_type=MODEL_TYPE,
        score_matrix=P,
        prior_matrix=Q,
        lambda_home=home_xg,          # v2: lambda_home == final home xG
        lambda_away=away_xg,
        rho=rho,
        fit_status=fit_status,
        loss=cal_error,
        converged=calib_converged,
        fitted_home_win=float(probs.get("home_win", 0.0)),
        fitted_draw=float(probs.get("draw", 0.0)),
        fitted_away_win=float(probs.get("away_win", 0.0)),
        prior_error=prior_error,
        calibrated_error=cal_error,
        max_single_market_error=max_err,
        kl_divergence=kl,
        tail_mass=tail_mass,
        diagnostics=diagnostics,
        model_version=MODEL_VERSION,
        fit_tier=tier,
        final_home_xg=home_xg,
        final_away_xg=away_xg,
        final_total_xg=home_xg + away_xg,
        actual_score_max=actual_score_max,
        candidate_score_max=candidate_score_max,
        constraint_count=len(constraints),
        max_constraint_error=max_err,
        market_coverage_score=build.market_coverage_score,
        market_reliability_weight=reliability,
        used_markets=build.used_markets,
        missing_markets=build.missing_markets,
        warnings=warnings,
    )


def _market_probs_to_dict(mp: MarketProbabilities) -> dict[str, float]:
    out = {}
    for attr in ("home_win", "draw", "away_win", "over_1_5", "under_1_5",
                 "over_2_5", "under_2_5", "over_3_5", "under_3_5"):
        v = getattr(mp, attr, None)
        if v is not None:
            out[attr] = float(v)
    return out


def _tail_mass(lh: float, la: float, max_goals: int) -> float:
    h = poisson.pmf(np.arange(max_goals + 1), lh)
    a = poisson.pmf(np.arange(max_goals + 1), la)
    return float(1.0 - np.outer(h, a).sum())


# ── main entry point ────────────────────────────────────────────────────────


def fit_market_score_model_v2(
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
) -> CalibratedModelResult:
    """Fit the V2 market score model. Never raises for missing markets — it
    degrades through the fallback tiers down to a neutral matrix."""
    warnings: list[str] = []
    I, J = np.indices((actual_score_max + 1, actual_score_max + 1))

    # 1. Build consensus constraints.
    if bookmaker_markets:
        build = build_constraints(
            bookmaker_markets,
            devig_method=devig_method,
            default_auto_devig=default_auto_devig,
            enable_asian_lines=enable_asian_lines,
        )
    else:
        build = _constraints_from_market_probs(market)
    constraints = build.constraints
    warnings.extend(build.warnings)

    coverage = build.coverage_by_family
    has_result = coverage.get("result", 0) > 0
    has_total = coverage.get("total_goals", 0) > 0
    tier = _classify_tier(coverage)

    # 2. Fundamental prior + reliability blend.
    fundamental = None
    if enable_fundamental:
        fundamental = build_fundamental_prior(fundamental_inputs or FundamentalInputs())
    n_families = len([f for f, n in coverage.items() if n > 0])
    avg_fresh = _avg_freshness(constraints)
    reliability = reliability_weight(_max_bookmaker_count(constraints), n_families, avg_fresh)

    # 3. Seed Dixon-Coles prior from market (blended with fundamental).
    mp_seed = _market_probs_from_constraints(constraints)
    lh_seed, la_seed = _seed_lambdas(mp_seed)
    rho = 0.0
    if has_result and has_total:
        try:
            dc = _fit_dc_params(mp_seed)
            lh_seed, la_seed, rho = dc.lh, dc.la, dc.rho
        except Exception as exc:
            warnings.append(f"DC seed fit failed ({exc}); using moment seed")

    if fundamental and reliability < 0.98:
        lh_seed = blend_mu(lh_seed, fundamental.mu_home, reliability if has_result else 0.2)
        la_seed = blend_mu(la_seed, fundamental.mu_away, reliability if has_result else 0.2)

    # 4. Build prior matrix Q.
    if not constraints and not (fundamental and enable_fundamental):
        Q = neutral_prior(actual_score_max)
        tier = "T6_neutral_fallback"
        warnings.append("No market or fundamental data; neutral fallback used.")
    else:
        Q = dc_prior(lh_seed, la_seed, rho, actual_score_max)

    prior_loss, _, prior_max_err = _constraint_loss(Q, I, J, constraints) if constraints else (0.0, 0.0, 0.0)
    prior_error = float(np.sqrt(prior_loss)) if prior_loss > 0 else 0.0

    # 5. Calibrate (only if we have constraints to calibrate to).
    if constraints:
        P, calib_converged, kl, cal_error, max_err, calib_params = _calibrate(Q, constraints, I, J)
    else:
        P, calib_converged, kl, cal_error, max_err, calib_params = Q, False, 0.0, 0.0, 0.0, {}

    # 6. Validation / rejection rules (spec §10.4).
    P, cal_error, max_err, kl, calib_params, reject_reason = _validate(
        P, Q, I, J, constraints, prior_error, cal_error, max_err, kl, calib_params)
    if reject_reason:
        warnings.append(reject_reason)
        calib_converged = False

    # 7. Tail mass + status.
    tail = _tail_mass(lh_seed, la_seed, actual_score_max)
    if tail > TAIL_MASS_STRONG_WARNING:
        warnings.append(f"High tail mass ({tail:.2%}); consider actual_score_max=15.")
    elif tail > TAIL_MASS_WARNING:
        warnings.append(f"Tail mass {tail:.2%} above target.")

    fit_status = _fit_status_for_tier(tier, cal_error, has_result)
    if tier in ("T0_rich", "T1_standard") and not has_result:
        fit_status = "weak"

    return _build_result(
        P, Q, constraints, build, tier, fit_status, lh_seed, la_seed, rho,
        prior_error, cal_error, kl, max_err, calib_converged,
        candidate_score_max, actual_score_max, tail, reliability, warnings,
        calib_params, fundamental,
    )


def _validate(P, Q, I, J, constraints, prior_error, cal_error, max_err, kl,
              calib_params):
    """Apply rejection rules; revert to prior Q if the calibration is bad."""
    reject = None
    bad = False
    if not np.all(np.isfinite(P)) or (P < 0).any():
        bad, reject = True, "Calibrated matrix invalid (nan/negative); reverted to prior."
    elif abs(P.sum() - 1.0) > 1e-6:
        bad, reject = True, "Calibrated matrix did not sum to 1; reverted to prior."
    elif constraints and cal_error > prior_error * 1.5 + 0.005:
        bad, reject = True, "Calibration worsened market fit; reverted to prior."
    else:
        home_xg = float((P * I).sum())
        away_xg = float((P * J).sum())
        if not (XG_BOUNDS_HOME[0] <= home_xg <= XG_BOUNDS_HOME[1]
                and XG_BOUNDS_AWAY[0] <= away_xg <= XG_BOUNDS_AWAY[1]
                and XG_BOUNDS_TOTAL[0] <= home_xg + away_xg <= XG_BOUNDS_TOTAL[1]):
            bad, reject = True, "Calibrated expected goals out of bounds; reverted to prior."

    if bad:
        loss, _, max_err2 = _constraint_loss(Q, I, J, constraints) if constraints else (0.0, 0.0, 0.0)
        return Q, prior_error, max_err2, 0.0, {}, reject
    return P, cal_error, max_err, kl, calib_params, None


def _constraints_from_market_probs(market: MarketProbabilities) -> ConstraintBuildResult:
    """Fallback constraint builder when only a MarketProbabilities consensus is
    available (no per-bookmaker markets). Treats the consensus as a single
    high-quality virtual bookmaker."""
    constraints: list[MarketConstraintInput] = []
    coverage: dict[str, int] = {}

    def add(ctype, family, target, target_type, side, line, weight):
        if target is None:
            return
        constraints.append(MarketConstraintInput(
            constraint_id=f"consensus:{ctype}:{line}",
            market_key="consensus",
            market_family=family,
            constraint_type=ctype,
            side=side,
            line=line,
            target_value=float(target),
            target_type=target_type,
            weight=weight,
            devig_method="consensus",
            bookmaker_count=1,
            source_bookmakers=["consensus"],
            quality_score=0.6,
            quality_label="medium",
        ))
        coverage[family] = coverage.get(family, 0) + 1

    if market.home_win is not None and market.draw is not None and market.away_win is not None:
        add("result_home_win", "result", market.home_win, "probability", "home", None, 1.5)
        add("result_draw", "result", market.draw, "probability", "draw", None, 1.5)
        add("result_away_win", "result", market.away_win, "probability", "away", None, 1.5)
    for line, (o, u) in {1.5: (market.over_1_5, market.under_1_5),
                         2.5: (market.over_2_5, market.under_2_5),
                         3.5: (market.over_3_5, market.under_3_5)}.items():
        add("total_over_half_line", "total_goals", o, "probability", "over", line, 1.25)
        add("total_under_half_line", "total_goals", u, "probability", "under", line, 1.25)

    families_present = set(coverage.keys())
    from .market_constraints import _COVERAGE_VALUE
    coverage_score = min(1.0, sum(v for f, v in _COVERAGE_VALUE.items() if f in families_present))
    used = []
    if coverage.get("result"):
        used.append("h2h")
    if coverage.get("total_goals"):
        used.append("totals")
    return ConstraintBuildResult(
        constraints=constraints,
        used_markets=used,
        missing_markets=["alternate_totals", "team_totals", "btts", "spreads"],
        coverage_by_family=coverage,
        market_coverage_score=coverage_score,
        warnings=[],
    )


def _avg_freshness(constraints) -> Optional[float]:
    vals = [c.freshness_minutes for c in constraints if c.freshness_minutes is not None]
    return sum(vals) / len(vals) if vals else None


def _max_bookmaker_count(constraints) -> int:
    return max((c.bookmaker_count for c in constraints), default=0)

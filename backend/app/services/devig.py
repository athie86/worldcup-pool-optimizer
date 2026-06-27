"""
De-vig / fair-probability layer  (spec WCPO-PRED-MODEL-V2 §6).

Converts raw bookmaker decimal odds into fair (margin-removed) probabilities
using several methods, with safe fallbacks. Every method returns a uniform
``DevigResult`` so downstream consensus/constraint code is method-agnostic.

Supported methods:
  - proportional   : divide implied probs by the booksum (overround removed evenly)
  - power           : p_i ∝ (1/o_i)^k, solve k so Σ p_i = 1 (favourite-longshot aware)
  - shin            : Shin (1992) insider-trading model
  - odds_ratio      : Cheung (2015) odds-ratio method
  - exchange_mid    : back/lay midpoint for exchanges, else proportional fallback
  - no_vig_manual_override : caller-supplied fair probs passed straight through
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import brentq


@dataclass
class DevigResult:
    probabilities: dict[str, float]
    fair_decimal_odds: dict[str, float]
    raw_implied_probabilities: dict[str, float]
    margin: float
    method: str
    converged: bool
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


SUPPORTED_METHODS = (
    "proportional",
    "power",
    "shin",
    "odds_ratio",
    "exchange_mid",
    "no_vig_manual_override",
)


def _implied(odds: dict[str, float]) -> dict[str, float]:
    return {k: 1.0 / o for k, o in odds.items() if o and o > 1.0}


def _finish(probs: dict[str, float], raw: dict[str, float], margin: float,
            method: str, converged: bool, warnings: list[str],
            diagnostics: Optional[dict] = None) -> DevigResult:
    fair_odds = {k: (1.0 / p if p > 1e-12 else float("inf")) for k, p in probs.items()}
    return DevigResult(
        probabilities=probs,
        fair_decimal_odds=fair_odds,
        raw_implied_probabilities=raw,
        margin=margin,
        method=method,
        converged=converged,
        warnings=warnings,
        diagnostics=diagnostics or {},
    )


# ── individual methods ──────────────────────────────────────────────────────


def devig_proportional(odds: dict[str, float]) -> DevigResult:
    raw = _implied(odds)
    booksum = sum(raw.values())
    if booksum <= 0 or len(raw) < 2:
        return _finish({}, raw, 0.0, "proportional", False,
                       ["proportional de-vig failed: invalid odds"])
    probs = {k: v / booksum for k, v in raw.items()}
    return _finish(probs, raw, booksum - 1.0, "proportional", True, [])


def devig_power(odds: dict[str, float]) -> DevigResult:
    """p_i ∝ (1/o_i)^k with k solved so probabilities sum to one."""
    raw = _implied(odds)
    if len(raw) < 2 or sum(raw.values()) <= 0:
        return _finish({}, raw, 0.0, "power", False,
                       ["power de-vig failed: invalid odds"])
    keys = list(raw.keys())
    r = np.array([raw[k] for k in keys], dtype=float)

    def f(k: float) -> float:
        return float(np.sum(np.power(r, k)) - 1.0)

    try:
        # booksum>1 → need k>1 to shrink; bracket generously
        k_star = brentq(f, 0.2, 8.0, maxiter=200)
        p = np.power(r, k_star)
        p = p / p.sum()
        probs = {keys[i]: float(p[i]) for i in range(len(keys))}
        return _finish(probs, raw, sum(raw.values()) - 1.0, "power", True, [],
                       {"power_k": k_star})
    except Exception as exc:  # pragma: no cover - falls back upstream
        return _finish({}, raw, 0.0, "power", False, [f"power de-vig failed: {exc}"])


def devig_shin(odds: dict[str, float]) -> DevigResult:
    """Shin (1992) model: removes margin assuming a fraction z of insider money."""
    raw = _implied(odds)
    if len(raw) < 2:
        return _finish({}, raw, 0.0, "shin", False, ["shin de-vig failed: invalid odds"])
    keys = list(raw.keys())
    pi = np.array([raw[k] for k in keys], dtype=float)
    booksum = float(pi.sum())
    if booksum <= 0:
        return _finish({}, raw, 0.0, "shin", False, ["shin de-vig failed: booksum<=0"])

    def shin_probs(z: float) -> np.ndarray:
        # p_i = (sqrt(z^2 + 4(1-z) pi_i^2 / booksum) - z) / (2(1-z))
        inside = z * z + 4.0 * (1.0 - z) * pi * pi / booksum
        return (np.sqrt(inside) - z) / (2.0 * (1.0 - z))

    def g(z: float) -> float:
        return float(shin_probs(z).sum() - 1.0)

    try:
        if booksum <= 1.0 + 1e-9:
            # No (or negative) margin → nothing to remove
            return devig_proportional(odds)
        z_star = brentq(g, 1e-6, 0.5, maxiter=200)
        p = shin_probs(z_star)
        p = p / p.sum()
        probs = {keys[i]: float(p[i]) for i in range(len(keys))}
        return _finish(probs, raw, booksum - 1.0, "shin", True, [], {"shin_z": z_star})
    except Exception:
        # Graceful fallback
        res = devig_power(odds)
        res.warnings.append("shin de-vig failed; fell back to power")
        res.method = "shin"
        return res


def devig_odds_ratio(odds: dict[str, float]) -> DevigResult:
    """Cheung odds-ratio method: OR * p/(1-p) = pi/(1-pi), solve OR so Σp=1."""
    raw = _implied(odds)
    if len(raw) < 2:
        return _finish({}, raw, 0.0, "odds_ratio", False,
                       ["odds_ratio de-vig failed: invalid odds"])
    keys = list(raw.keys())
    pi = np.array([raw[k] for k in keys], dtype=float)
    pi = np.clip(pi, 1e-9, 1 - 1e-9)

    def probs_for(or_: float) -> np.ndarray:
        # p = pi / (or_ + pi - or_*pi)
        return pi / (or_ + pi - or_ * pi)

    def h(or_: float) -> float:
        return float(probs_for(or_).sum() - 1.0)

    try:
        or_star = brentq(h, 1e-3, 1000.0, maxiter=200)
        p = probs_for(or_star)
        p = p / p.sum()
        probs = {keys[i]: float(p[i]) for i in range(len(keys))}
        return _finish(probs, raw, float(pi.sum()) - 1.0, "odds_ratio", True, [],
                       {"odds_ratio": or_star})
    except Exception:
        res = devig_proportional(odds)
        res.warnings.append("odds_ratio de-vig failed; fell back to proportional")
        res.method = "odds_ratio"
        return res


def devig_exchange_mid(
    back_odds: dict[str, float],
    lay_odds: Optional[dict[str, float]] = None,
) -> DevigResult:
    """Use the back/lay midpoint implied probability; proportional fallback."""
    if not lay_odds:
        res = devig_proportional(back_odds)
        res.method = "exchange_mid"
        res.warnings.append("no lay odds available; used proportional on back odds")
        return res
    raw_back = _implied(back_odds)
    raw_lay = _implied(lay_odds)
    mids: dict[str, float] = {}
    for k in raw_back:
        if k in raw_lay:
            mids[k] = 0.5 * (raw_back[k] + raw_lay[k])
        else:
            mids[k] = raw_back[k]
    booksum = sum(mids.values())
    if booksum <= 0:
        return _finish({}, raw_back, 0.0, "exchange_mid", False,
                       ["exchange_mid failed: invalid odds"])
    probs = {k: v / booksum for k, v in mids.items()}
    return _finish(probs, raw_back, booksum - 1.0, "exchange_mid", True, [])


# ── dispatcher with fallbacks (spec §6.2/§6.3) ──────────────────────────────


def devig(
    odds: dict[str, float],
    method: str = "power",
    *,
    lay_odds: Optional[dict[str, float]] = None,
    manual_probabilities: Optional[dict[str, float]] = None,
) -> DevigResult:
    """De-vig ``odds`` with the requested method, falling back safely.

    Fallback order (spec §6.3): selected → power → proportional → drop+warn.
    """
    if method == "no_vig_manual_override" and manual_probabilities:
        total = sum(manual_probabilities.values()) or 1.0
        probs = {k: v / total for k, v in manual_probabilities.items()}
        return _finish(probs, dict(manual_probabilities), 0.0,
                       "no_vig_manual_override", True, [])

    if method == "exchange_mid" or (lay_odds and method == "auto"):
        res = devig_exchange_mid(odds, lay_odds)
        if res.converged:
            return res

    dispatch = {
        "proportional": devig_proportional,
        "power": devig_power,
        "shin": devig_shin,
        "odds_ratio": devig_odds_ratio,
    }
    chosen = method if method in dispatch else "power"

    res = dispatch[chosen](odds)
    if res.converged:
        return res

    if chosen != "power":
        res = devig_power(odds)
        if res.converged:
            res.warnings.append(f"{method} de-vig failed; used power")
            return res

    res = devig_proportional(odds)
    if res.converged:
        res.warnings.append(f"{method} de-vig failed; used proportional")
        return res

    res.warnings.append("all de-vig methods failed; market dropped")
    return res

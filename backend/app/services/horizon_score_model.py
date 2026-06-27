"""Horizon-consistent knockout score model service (spec Phase 3).

Wraps the existing 90-minute engine (model registry → V2 → V1 → fallback) as the
``P90`` source and builds the full horizon model around it:

  P90  → extra-time conditional distribution PET
       → penalty shootout probability q (market-inferred when possible)
       → terminal-state distribution
       → score_matrix_90 / score_matrix_120 / advancement diagnostics

It never raises for missing knockout markets — it degrades through explicit fit
tiers (H0 rich … H5 neutral) so a single match can never abort a model run.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .score_model import CalibratedModelResult, MarketProbabilities, matrix_market_probs
from .fundamental_prior import FundamentalInputs
from .odds_normalization import BookmakerMarket
from .devig import devig
from . import horizon as H
from .horizon import (
    HorizonModelResult,
    ScoringBasis,
    build_extra_time_distribution,
    build_terminal_states,
    derive_score_matrix_90,
    derive_score_matrix_120,
    summarize_terminal_states,
    validate_terminal_states,
    infer_penalty_probability,
)

MODEL_TYPE = "horizon_score_model"
MODEL_VERSION = "3.0.0"


# ── Knockout market parsing (defensive; provider keys vary) ──────────────────

# Aliases for the optional knockout markets. The Odds API may not expose these
# under these exact keys, so admin imports / overrides can supply any alias.
_ADVANCE_KEYS = frozenset({"to_qualify", "qualify", "advance", "to_advance", "team_to_advance"})
_ET_KEYS = frozenset({"goes_to_extra_time", "extra_time", "to_go_to_extra_time"})
_PENS_KEYS = frozenset({"goes_to_penalties", "to_go_to_penalties", "penalties"})
_PEN_WINNER_KEYS = frozenset({"penalty_shootout_winner", "shootout_winner", "penalty_winner"})


def _two_way_probs(bm: BookmakerMarket, devig_method: str) -> Optional[dict[str, float]]:
    """De-vig a simple two-way market keyed by outcome_type."""
    odds = {
        o.outcome_type: float(o.price_decimal)
        for o in bm.outcomes
        if o.price_decimal and o.price_decimal > 1.0
    }
    if len(odds) < 2:
        return None
    res = devig(odds, method=devig_method if devig_method != "auto" else "power")
    if not res.converged:
        return None
    return res.probabilities


def _extract_knockout_markets(
    bookmaker_markets: Optional[list[BookmakerMarket]],
    devig_method: str,
) -> dict[str, float]:
    """Consensus knockout-market probabilities, averaged across bookmakers.

    Returns a dict with any of: ``p_home_adv``, ``p_away_adv``, ``p_extra_time``,
    ``p_penalties``, ``q_home`` (P home wins shootout), ``bookmaker_count``.
    """
    out: dict[str, list[float]] = {
        "p_home_adv": [], "p_away_adv": [],
        "p_extra_time": [], "p_penalties": [], "q_home": [],
    }
    if not bookmaker_markets:
        return {}

    for bm in bookmaker_markets:
        key = (bm.market_key or "").lower()
        probs = None
        if key in _ADVANCE_KEYS:
            probs = _two_way_probs(bm, devig_method)
            if probs:
                if "home_win" in probs or "home" in probs:
                    out["p_home_adv"].append(probs.get("home_win", probs.get("home", 0.0)))
                if "away_win" in probs or "away" in probs:
                    out["p_away_adv"].append(probs.get("away_win", probs.get("away", 0.0)))
        elif key in _PEN_WINNER_KEYS:
            probs = _two_way_probs(bm, devig_method)
            if probs:
                q = probs.get("home_win", probs.get("home"))
                if q is not None:
                    out["q_home"].append(q)
        elif key in _ET_KEYS:
            probs = _two_way_probs(bm, devig_method)
            if probs and ("yes" in probs):
                out["p_extra_time"].append(probs["yes"])
        elif key in _PENS_KEYS:
            probs = _two_way_probs(bm, devig_method)
            if probs and ("yes" in probs):
                out["p_penalties"].append(probs["yes"])

    result: dict[str, float] = {}
    count = 0
    for k, vals in out.items():
        if vals:
            result[k] = float(np.mean(vals))
            count = max(count, len(vals))
    if count:
        result["bookmaker_count"] = count
    return result


# ── Fit tier classification ─────────────────────────────────────────────────


def _classify_tier(ko: dict[str, float], p90_tier: Optional[str]) -> str:
    has_adv = "p_home_adv" in ko or "p_away_adv" in ko
    has_pen = "q_home" in ko
    has_et = "p_extra_time" in ko or "p_penalties" in ko
    if has_adv and (has_pen or has_et):
        return "H0_rich_terminal"
    if has_adv:
        return "H1_advancement"
    if has_et:
        return "H2_extra_time"
    if p90_tier == "T6_neutral_fallback":
        return "H5_neutral"
    return "H3_score_only"


# ── Main entry point ─────────────────────────────────────────────────────────


def build_horizon_result_from_p90(
    p90_fit: CalibratedModelResult,
    *,
    scoring_basis: ScoringBasis | str,
    bookmaker_markets: Optional[list[BookmakerMarket]] = None,
    et_score_max: int = H.DEFAULT_ET_MAX,
    et_rate: float = H.DEFAULT_ET_RATE,
    devig_method: str = "power",
) -> HorizonModelResult:
    """Assemble a :class:`HorizonModelResult` around an already-fitted P90 matrix."""
    warnings: list[str] = list(getattr(p90_fit, "warnings", []) or [])

    p90 = np.asarray(p90_fit.score_matrix, dtype=float)
    n = p90.shape[0]
    lam_h = float(p90_fit.lambda_home)
    lam_a = float(p90_fit.lambda_away)

    # 90-minute result probabilities straight from P90.
    p90_probs = matrix_market_probs(p90)
    p_home_90 = p90_probs["home_win"]
    p_draw_90 = p90_probs["draw"]
    p_away_90 = p90_probs["away_win"]

    # Extra-time conditional distribution.
    pet = build_extra_time_distribution(lam_h, lam_a, et_score_max, r_et=et_rate)
    p_home_et = float(np.tril(pet, -1).sum())   # home_et > away_et
    p_away_et = float(np.triu(pet, 1).sum())    # away_et > home_et
    p_still_draw_et = float(np.trace(pet))

    # Knockout market inference.
    ko = _extract_knockout_markets(bookmaker_markets, devig_method)
    p_home_adv_market = ko.get("p_home_adv")
    if p_home_adv_market is None and "p_away_adv" in ko:
        p_home_adv_market = 1.0 - ko["p_away_adv"]
    reliability = min(1.0, ko.get("bookmaker_count", 0) / 3.0)

    if "q_home" in ko:
        q = float(np.clip(ko["q_home"], 0.05, 0.95))
    else:
        q = infer_penalty_probability(
            lam_h, lam_a,
            p_home_win_90=p_home_90,
            p_draw_90=p_draw_90,
            p_home_wins_et_given_et=p_home_et,
            p_still_draw_after_et_given_et=p_still_draw_et,
            p_home_adv_market=p_home_adv_market,
            reliability=reliability,
        )

    # Terminal states + derived surfaces.
    states = build_terminal_states(p90, pet, q)
    n120 = n + et_score_max
    score_matrix_90 = derive_score_matrix_90(states, n)
    score_matrix_120 = derive_score_matrix_120(states, n120)
    summary = summarize_terminal_states(states)
    warnings += validate_terminal_states(
        states, score_matrix_90, score_matrix_120, summary,
    )

    tier = _classify_tier(ko, getattr(p90_fit, "fit_tier", None))

    diagnostics = dict(getattr(p90_fit, "diagnostics", {}) or {})
    diagnostics.update({
        "horizon_model_type": MODEL_TYPE,
        "horizon_model_version": MODEL_VERSION,
        "horizon_fit_tier": tier,
        "horizon_constraints": ko,
        "p90_summary": {
            "home_win": p_home_90, "draw": p_draw_90, "away_win": p_away_90,
        },
        "p120_summary": {
            "home_win": summary.p_home_win_120,
            "draw": summary.p_draw_120,
            "away_win": summary.p_away_win_120,
        },
        "terminal_probabilities": {
            "p_goes_to_extra_time": summary.p_goes_to_extra_time,
            "p_goes_to_penalties": summary.p_goes_to_penalties,
            "p_home_advances": summary.p_home_advances,
            "p_away_advances": summary.p_away_advances,
            "p_home_wins_penalties_given_pens": q,
            "p_away_wins_penalties_given_pens": 1.0 - q,
        },
        "advancement_summary": {
            "p_home_advances": summary.p_home_advances,
            "p_away_advances": summary.p_away_advances,
            "et_rate": et_rate,
        },
        "warnings": warnings,
    })

    return HorizonModelResult(
        model_type=MODEL_TYPE,
        model_version=MODEL_VERSION,
        score_matrix_90=score_matrix_90,
        score_matrix_120=score_matrix_120,
        terminal_states=states,
        p_home_win_90=p_home_90,
        p_draw_90=p_draw_90,
        p_away_win_90=p_away_90,
        p_home_win_120=summary.p_home_win_120,
        p_draw_120=summary.p_draw_120,
        p_away_win_120=summary.p_away_win_120,
        p_goes_to_extra_time=summary.p_goes_to_extra_time,
        p_goes_to_penalties=summary.p_goes_to_penalties,
        p_home_advances=summary.p_home_advances,
        p_away_advances=summary.p_away_advances,
        p_home_wins_penalties_given_pens=q,
        p_away_wins_penalties_given_pens=1.0 - q,
        diagnostics=diagnostics,
        fit_tier=tier,
        lambda_home=lam_h,
        lambda_away=lam_a,
    )


def fit_horizon_score_model(
    market: MarketProbabilities,
    bookmaker_markets: Optional[list[BookmakerMarket]] = None,
    *,
    fundamental_inputs: Optional[FundamentalInputs] = None,
    scoring_basis: ScoringBasis | str = ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES,
    model_version: str = "v2",
    actual_score_max: int = 12,
    et_score_max: int = H.DEFAULT_ET_MAX,
    candidate_score_max: int = 5,
    devig_method: str = "auto",
    default_auto_devig: str = "power",
    enable_fundamental: bool = True,
    enable_asian_lines: bool = True,
    v1_fallback_enabled: bool = True,
) -> tuple[CalibratedModelResult, HorizonModelResult]:
    """Fit the 90-minute engine, then build the full horizon model around it.

    Returns ``(p90_fit, horizon_result)``. The P90 fit is returned alongside so
    callers can persist the existing V2 fields (xg, used markets, etc.) unchanged.
    """
    # Local import avoids a circular import (registry imports this module).
    from . import model_registry

    p90_fit = model_registry.fit(
        model_version,
        market,
        bookmaker_markets,
        fundamental_inputs=fundamental_inputs,
        actual_score_max=actual_score_max,
        candidate_score_max=candidate_score_max,
        devig_method=devig_method,
        default_auto_devig=default_auto_devig,
        enable_fundamental=enable_fundamental,
        enable_asian_lines=enable_asian_lines,
        v1_fallback_enabled=v1_fallback_enabled,
    )
    horizon = build_horizon_result_from_p90(
        p90_fit,
        scoring_basis=scoring_basis,
        bookmaker_markets=bookmaker_markets,
        et_score_max=et_score_max,
        devig_method=default_auto_devig if devig_method == "auto" else devig_method,
    )
    return p90_fit, horizon

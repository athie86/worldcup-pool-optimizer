"""
Market constraint layer  (spec WCPO-PRED-MODEL-V2 §7/§8).

Turns the available bookmaker markets for one match into a list of de-vigged,
bookmaker-weighted, consensus ``MarketConstraintInput`` objects that the V2
score model calibrates against.

Input is the ``BookmakerMarket`` dataclass already used by the app
(``odds_normalization.BookmakerMarket``) so this layer plugs into the existing
data flow without requiring richer ingestion. When richer markets are present
(team totals, btts, spreads, …) they are used automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import odds_quality as oq
from .devig import devig
from .market_parsing import canonical_family
from .odds_normalization import BookmakerMarket, RawOutcome


@dataclass
class MarketConstraintInput:
    constraint_id: str
    market_key: str
    market_family: str
    constraint_type: str
    side: Optional[str]
    line: Optional[float]
    target_value: float
    target_type: str            # probability | conditional_probability
    weight: float
    devig_method: str
    bookmaker_count: int
    source_bookmakers: list[str] = field(default_factory=list)
    freshness_minutes: Optional[float] = None
    quality_score: float = 0.0
    quality_label: str = "low"
    source_details: dict = field(default_factory=dict)


@dataclass
class ConstraintBuildResult:
    constraints: list[MarketConstraintInput]
    used_markets: list[str]
    missing_markets: list[str]
    coverage_by_family: dict[str, int]
    market_coverage_score: float
    warnings: list[str] = field(default_factory=list)


def _half_line(line: float) -> bool:
    return abs((line * 2) - round(line * 2)) < 1e-6 and abs(line - round(line)) > 1e-6


def _quarter_line(line: float) -> bool:
    frac = abs(line - round(line))
    return abs(frac - 0.25) < 1e-6 or abs(frac - 0.75) < 1e-6


def _integer_line(line: float) -> bool:
    return abs(line - round(line)) < 1e-6


# Coverage scoring: which families meaningfully improve the fit, and how much.
_COVERAGE_VALUE = {
    "result": 0.40,
    "total_goals": 0.30,
    "team_goals": 0.12,
    "both_teams_to_score": 0.08,
    "result_conditional_no_draw": 0.05,
    "goal_difference": 0.05,
}


def _devig_method_for(family: str, requested: str, default_auto: str) -> str:
    if requested and requested != "auto":
        return requested
    return default_auto


def build_constraints(
    bookmaker_markets: list[BookmakerMarket],
    *,
    devig_method: str = "auto",
    default_auto_devig: str = "power",
    enable_asian_lines: bool = True,
) -> ConstraintBuildResult:
    """Build consensus market constraints from per-bookmaker markets."""
    warnings: list[str] = []

    # Group bookmaker markets by (family, line) → list of (bk_key, fair_probs, last_update)
    # fair_probs maps canonical outcome_type → probability.
    groups: dict[tuple[str, Optional[float]], list[dict]] = {}
    used_market_keys: set[str] = set()

    for bm in bookmaker_markets:
        family = canonical_family(bm.market_key)
        if family not in _COVERAGE_VALUE:
            continue  # first-half / exchange / unknown — not used in FT score model
        method = _devig_method_for(family, devig_method, default_auto_devig)

        # Build odds dict for this bookmaker market keyed by canonical outcome_type
        odds = {o.outcome_type: o.price_decimal for o in bm.outcomes
                if o.outcome_type not in ("unknown", None) and o.price_decimal and o.price_decimal > 1.0}
        if len(odds) < 2:
            continue

        # 3-way result must keep all three; 2-way families need both sides
        dres = devig(odds, method=method)
        if not dres.probabilities:
            warnings.append(f"de-vig failed for {bm.market_key} ({bm.bookmaker_key})")
            continue

        line = bm.line
        used_market_keys.add(bm.market_key)
        groups.setdefault((bm.market_key, line), []).append({
            "bookmaker_key": bm.bookmaker_key,
            "probs": dres.probabilities,
            "last_update": bm.last_update,
            "devig_method": dres.method,
        })

    constraints: list[MarketConstraintInput] = []
    coverage_by_family: dict[str, int] = {}

    # Build constraints per (market_key, line) group
    for (market_key, line), entries in groups.items():
        family = canonical_family(market_key)
        specs = _constraint_specs(family, line, enable_asian_lines, warnings)
        if not specs:
            continue
        for spec in specs:
            ctype, otype_key, target_type, side = spec
            cons = _consensus_constraint(
                market_key, family, ctype, otype_key, target_type, side, line,
                entries,
            )
            if cons is not None:
                constraints.append(cons)
                coverage_by_family[family] = coverage_by_family.get(family, 0) + 1

    used_markets = sorted(used_market_keys)
    families_present = set(coverage_by_family.keys())
    coverage_score = sum(v for f, v in _COVERAGE_VALUE.items() if f in families_present)
    coverage_score = min(1.0, coverage_score)

    all_keys = {"h2h", "h2h_3_way", "totals", "alternate_totals", "team_totals",
                "alternate_team_totals", "btts", "draw_no_bet", "spreads",
                "alternate_spreads"}
    missing_markets = sorted(all_keys - used_market_keys)

    return ConstraintBuildResult(
        constraints=constraints,
        used_markets=used_markets,
        missing_markets=missing_markets,
        coverage_by_family=coverage_by_family,
        market_coverage_score=coverage_score,
        warnings=warnings,
    )


def _constraint_specs(family: str, line: Optional[float], enable_asian: bool,
                      warnings: list[str]):
    """Return list of (constraint_type, prob_key, target_type, side) for a family."""
    if family == "result":
        return [
            ("result_home_win", "home_win", "probability", "home"),
            ("result_draw", "draw", "probability", "draw"),
            ("result_away_win", "away_win", "probability", "away"),
        ]
    if family == "both_teams_to_score":
        return [
            ("btts_yes", "btts_yes", "probability", "yes"),
            ("btts_no", "btts_no", "probability", "no"),
        ]
    if family == "result_conditional_no_draw":
        return [
            ("draw_no_bet_home", "home_dnb", "conditional_probability", "home"),
            ("draw_no_bet_away", "away_dnb", "conditional_probability", "away"),
        ]
    if line is None:
        return []
    if family == "total_goals":
        if _half_line(line):
            return [
                ("total_over_half_line", "over", "probability", "over"),
                ("total_under_half_line", "under", "probability", "under"),
            ]
        if _integer_line(line):
            return [
                ("total_over_integer_line", "over", "conditional_probability", "over"),
                ("total_under_integer_line", "under", "conditional_probability", "under"),
            ]
        if _quarter_line(line):
            if enable_asian:
                # Approximate quarter line by its two adjacent half-lines via
                # conditional handling at the rounded line; keep as conditional.
                return [
                    ("total_over_integer_line", "over", "conditional_probability", "over"),
                    ("total_under_integer_line", "under", "conditional_probability", "under"),
                ]
            warnings.append(f"quarter total line {line} dropped (asian lines disabled)")
            return []
    if family == "team_goals":
        if _half_line(line):
            return [
                ("team_total_home_over_half_line", "home_over", "probability", "home"),
                ("team_total_home_under_half_line", "home_under", "probability", "home"),
                ("team_total_away_over_half_line", "away_over", "probability", "away"),
                ("team_total_away_under_half_line", "away_under", "probability", "away"),
            ]
        return []  # integer team totals are rarer; skip safely
    if family == "goal_difference":
        if _half_line(line):
            return [
                ("spread_home_half_line", "home_spread", "probability", "home"),
                ("spread_away_half_line", "away_spread", "probability", "away"),
            ]
        warnings.append(f"non-half spread line {line} dropped (push mechanics)")
        return []
    return []


def _consensus_constraint(market_key, family, ctype, prob_key, target_type, side,
                          line, entries) -> Optional[MarketConstraintInput]:
    values: list[float] = []
    base_weights: list[float] = []
    bk_keys: list[str] = []
    fresh_list: list[float] = []
    methods: set[str] = set()

    for e in entries:
        p = e["probs"].get(prob_key)
        if p is None:
            continue
        bw = oq.bookmaker_weight(e["bookmaker_key"])
        fw, age = oq.freshness_weight(e["last_update"])
        w = bw * fw * oq.market_family_weight(family)
        values.append(float(p))
        base_weights.append(w)
        bk_keys.append(e["bookmaker_key"])
        if age is not None:
            fresh_list.append(age)
        methods.add(e["devig_method"])

    if not values:
        return None

    # Outlier downweighting against the median target value
    ow = oq.outlier_weights(values)
    weights = [bw * o for bw, o in zip(base_weights, ow)]
    total_w = sum(weights)
    if total_w <= 0:
        return None

    target = sum(v * w for v, w in zip(values, weights)) / total_w

    # Family cap on the aggregate constraint weight
    capped_w = oq.apply_family_cap(family, total_w)
    quality_score = min(1.0, total_w / 3.0)
    freshness_minutes = (sum(fresh_list) / len(fresh_list)) if fresh_list else None
    outlier_conflict = any(o < 0.5 for o in ow)
    label = oq.quality_label(len(bk_keys), freshness_minutes, outlier_conflict)

    return MarketConstraintInput(
        constraint_id=f"{market_key}:{line}:{ctype}",
        market_key=market_key,
        market_family=family,
        constraint_type=ctype,
        side=side,
        line=line,
        target_value=float(target),
        target_type=target_type,
        weight=float(capped_w),
        devig_method=",".join(sorted(methods)),
        bookmaker_count=len(bk_keys),
        source_bookmakers=bk_keys,
        freshness_minutes=freshness_minutes,
        quality_score=quality_score,
        quality_label=label,
        source_details={"raw_targets": values, "weights": weights},
    )

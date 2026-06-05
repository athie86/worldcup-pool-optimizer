from dataclasses import dataclass, field
from typing import Optional
from .poisson_model import MarketProbabilities


@dataclass
class RawOutcome:
    outcome_type: str  # home_win, draw, away_win, over, under
    price_decimal: float
    line: Optional[float] = None


@dataclass
class BookmakerMarket:
    bookmaker_key: str
    market_key: str  # h2h or totals
    line: Optional[float]
    outcomes: list[RawOutcome]
    last_update: Optional[object] = None


def normalize_market(outcomes: list[RawOutcome]) -> dict[str, float]:
    """Apply proportional margin removal to a set of outcomes."""
    raw = {o.outcome_type: 1.0 / o.price_decimal for o in outcomes if o.price_decimal > 0}
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}


def is_complete_h2h(outcomes: list[RawOutcome]) -> bool:
    types = {o.outcome_type for o in outcomes}
    return {"home_win", "draw", "away_win"}.issubset(types)


def is_complete_totals(outcomes: list[RawOutcome]) -> bool:
    types = {o.outcome_type for o in outcomes}
    return {"over", "under"}.issubset(types)


def compute_consensus(
    bookmaker_markets: list[BookmakerMarket],
    overrides: list[RawOutcome] | None = None,
) -> MarketProbabilities:
    """Compute consensus market probabilities from bookmaker markets and overrides."""
    # Group by market_key and line
    h2h_probs: list[dict] = []
    totals_probs: dict[float, list[dict]] = {}

    for bm in bookmaker_markets:
        if bm.market_key == "h2h":
            if not is_complete_h2h(bm.outcomes):
                continue
            norm = normalize_market(bm.outcomes)
            if norm:
                h2h_probs.append(norm)
        elif bm.market_key == "totals":
            line = bm.line
            if line is None:
                continue
            if not is_complete_totals(bm.outcomes):
                continue
            norm = normalize_market(bm.outcomes)
            if norm:
                if line not in totals_probs:
                    totals_probs[line] = []
                totals_probs[line].append(norm)

    # Apply overrides: override replaces fetched odds for that market/line/outcome
    if overrides:
        h2h_override_outcomes = [o for o in overrides if o.line is None]
        totals_overrides: dict[float, list[RawOutcome]] = {}
        for o in overrides:
            if o.line is not None:
                if o.line not in totals_overrides:
                    totals_overrides[o.line] = []
                totals_overrides[o.line].append(o)

        if h2h_override_outcomes and is_complete_h2h(h2h_override_outcomes):
            h2h_probs = [normalize_market(h2h_override_outcomes)]

        for line, outs in totals_overrides.items():
            if is_complete_totals(outs):
                totals_probs[line] = [normalize_market(outs)]

    # Average
    result = MarketProbabilities()

    if h2h_probs:
        result.home_win = float(sum(p.get("home_win", 0) for p in h2h_probs) / len(h2h_probs))
        result.draw = float(sum(p.get("draw", 0) for p in h2h_probs) / len(h2h_probs))
        result.away_win = float(sum(p.get("away_win", 0) for p in h2h_probs) / len(h2h_probs))

    for line, probs_list in totals_probs.items():
        avg_over = float(sum(p.get("over", 0) for p in probs_list) / len(probs_list))
        avg_under = float(sum(p.get("under", 0) for p in probs_list) / len(probs_list))
        if abs(line - 1.5) < 0.01:
            result.over_1_5 = avg_over
            result.under_1_5 = avg_under
        elif abs(line - 2.5) < 0.01:
            result.over_2_5 = avg_over
            result.under_2_5 = avg_under
        elif abs(line - 3.5) < 0.01:
            result.over_3_5 = avg_over
            result.under_3_5 = avg_under

    return result

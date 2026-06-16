"""
Canonical market parser  (spec WCPO-PRED-MODEL-V2 §13.3/§13.4).

Maps raw Odds-API market keys + outcomes onto a canonical representation the
constraint layer understands. Designed to be tolerant: unknown markets and
unknown outcome names are preserved as ``unknown`` rather than raising, so
ingestion never crashes on a market schema it has not seen before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# market_key → canonical family
MARKET_FAMILY: dict[str, str] = {
    "h2h": "result",
    "h2h_3_way": "result",
    "totals": "total_goals",
    "alternate_totals": "total_goals",
    "team_totals": "team_goals",
    "alternate_team_totals": "team_goals",
    "btts": "both_teams_to_score",
    "draw_no_bet": "result_conditional_no_draw",
    "spreads": "goal_difference",
    "alternate_spreads": "goal_difference",
    "h2h_lay": "exchange_lay_result",
    # first-half markets are stored but not used in the full-time score model
    "h2h_h1": "first_half",
    "h2h_3_way_h1": "first_half",
    "totals_h1": "first_half",
}

SUPPORTED_FAMILIES = {
    "result",
    "total_goals",
    "team_goals",
    "both_teams_to_score",
    "result_conditional_no_draw",
    "goal_difference",
}


@dataclass
class CanonicalOutcome:
    outcome_type: str            # canonical type, e.g. home_win / over / home_over / btts_yes
    price_decimal: float
    line: Optional[float] = None
    side: Optional[str] = None   # home / away / over / under / yes / no when meaningful
    raw_name: Optional[str] = None
    description: Optional[str] = None
    point: Optional[float] = None


@dataclass
class CanonicalMarket:
    market_key: str
    market_family: str
    line: Optional[float]
    outcomes: list[CanonicalOutcome] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    supported: bool = True


def canonical_family(market_key: str) -> str:
    return MARKET_FAMILY.get(market_key, "unknown")


def _num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_line(name: str, point, description: Optional[str]) -> Optional[float]:
    pt = _num(point)
    if pt is not None:
        return pt
    for text in (description, name):
        if not text:
            continue
        m = re.search(r"[-+]?\d+\.?\d*", text)
        if m:
            return float(m.group(0))
    return None


def _classify_result(name: str, home_team: str, away_team: str) -> str:
    n = (name or "").strip().lower()
    if n in ("draw", "the draw", "tie", "x"):
        return "draw"
    if home_team and (n == home_team.lower() or home_team.lower() in n or n in home_team.lower()):
        return "home_win"
    if away_team and (n == away_team.lower() or away_team.lower() in n or n in away_team.lower()):
        return "away_win"
    return "unknown"


def _classify_over_under(name: str) -> Optional[str]:
    n = (name or "").strip().lower()
    if n.startswith("over") or n == "o":
        return "over"
    if n.startswith("under") or n == "u":
        return "under"
    return None


def _classify_yes_no(name: str) -> Optional[str]:
    n = (name or "").strip().lower()
    if n in ("yes", "y"):
        return "yes"
    if n in ("no", "n"):
        return "no"
    return None


def parse_market(
    market_key: str,
    outcomes: list[dict],
    home_team: str,
    away_team: str,
) -> CanonicalMarket:
    """Parse one bookmaker market's outcomes into canonical outcomes.

    ``outcomes`` is a list of dicts with keys: name, price, point, description.
    Unknown markets are returned with ``supported=False`` but still carry their
    raw outcomes so callers can persist them.
    """
    family = canonical_family(market_key)
    cm = CanonicalMarket(market_key=market_key, market_family=family, line=None,
                         supported=family in SUPPORTED_FAMILIES)

    for o in outcomes:
        name = o.get("name", "")
        price = _num(o.get("price"))
        if price is None or price <= 1.0:
            continue
        description = o.get("description")
        point = o.get("point")
        line = _extract_line(name, point, description)

        otype, side = "unknown", None

        if family == "result":
            otype = _classify_result(name, home_team, away_team)
            side = {"home_win": "home", "away_win": "away", "draw": "draw"}.get(otype)
            line = None
        elif family == "total_goals":
            ou = _classify_over_under(name)
            if ou:
                otype, side = ou, ou
        elif family == "team_goals":
            # description usually names the team; name is Over/Under
            ou = _classify_over_under(name)
            team_text = (description or "").lower()
            team_side = None
            if home_team and home_team.lower() in team_text:
                team_side = "home"
            elif away_team and away_team.lower() in team_text:
                team_side = "away"
            if ou and team_side:
                otype = f"{team_side}_{ou}"
                side = team_side
        elif family == "both_teams_to_score":
            yn = _classify_yes_no(name)
            if yn:
                otype, side = f"btts_{yn}", yn
            line = None
        elif family == "result_conditional_no_draw":
            res = _classify_result(name, home_team, away_team)
            if res == "home_win":
                otype, side = "home_dnb", "home"
            elif res == "away_win":
                otype, side = "away_dnb", "away"
            line = None
        elif family == "goal_difference":
            res = _classify_result(name, home_team, away_team)
            if res == "home_win":
                otype, side = "home_spread", "home"
            elif res == "away_win":
                otype, side = "away_spread", "away"
        else:
            cm.warnings.append(f"unsupported market family for key '{market_key}'")

        cm.outcomes.append(CanonicalOutcome(
            outcome_type=otype,
            price_decimal=price,
            line=line,
            side=side,
            raw_name=name,
            description=description,
            point=_num(point),
        ))

    # Single representative line for total/team/spread markets (for display)
    lines = {oc.line for oc in cm.outcomes if oc.line is not None}
    if len(lines) == 1:
        cm.line = next(iter(lines))
    return cm

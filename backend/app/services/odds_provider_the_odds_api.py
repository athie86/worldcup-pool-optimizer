from __future__ import annotations
import re
from datetime import datetime
from typing import Optional
import httpx
from .odds_provider_base import (
    OddsProvider,
    ProviderEvent,
    ProviderOddsEvent,
    ProviderBookmaker,
    ProviderMarket,
    ProviderOutcome,
)

BASE_URL = "https://api.the-odds-api.com/v4"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_totals_line(name: str) -> Optional[float]:
    """Extract the line from an outcome name like 'Over 2.5' -> 2.5"""
    m = re.search(r"(\d+\.?\d*)", name)
    if m:
        return float(m.group(1))
    return None


def _outcome_type_h2h(name: str, home_team: str, away_team: str) -> str:
    if name.lower() in ("the draw", "draw"):
        return "draw"
    if name == home_team:
        return "home_win"
    if name == away_team:
        return "away_win"
    # Fuzzy fallback: compare lowercased substrings
    name_lower = name.lower()
    home_lower = home_team.lower()
    away_lower = away_team.lower()
    if name_lower in home_lower or home_lower in name_lower:
        return "home_win"
    if name_lower in away_lower or away_lower in name_lower:
        return "away_win"
    return "unknown"


def _outcome_type_totals(name: str) -> str:
    name_lower = name.lower()
    if name_lower.startswith("over"):
        return "over"
    if name_lower.startswith("under"):
        return "under"
    return "unknown"


class TheOddsApiProvider(OddsProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def fetch_events(self, sport_key: str, **kwargs) -> list[ProviderEvent]:
        url = f"{BASE_URL}/sports/{sport_key}/events"
        params = {"apiKey": self.api_key, "dateFormat": "iso"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        events = []
        for item in data:
            events.append(
                ProviderEvent(
                    id=item["id"],
                    sport_key=item.get("sport_key", sport_key),
                    home_team=item["home_team"],
                    away_team=item["away_team"],
                    commence_time=_parse_dt(item.get("commence_time")),
                )
            )
        return events

    async def fetch_odds(
        self,
        sport_key: str,
        markets: list[str],
        regions: list[str] | None = None,
        bookmakers: list[str] | None = None,
        commence_time_from: datetime | None = None,
        commence_time_to: datetime | None = None,
    ) -> tuple[list[ProviderOddsEvent], str, dict]:
        url = f"{BASE_URL}/sports/{sport_key}/odds"
        params: dict = {
            "apiKey": self.api_key,
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        if regions:
            params["regions"] = ",".join(regions)
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)
        if commence_time_from:
            params["commenceTimeFrom"] = commence_time_from.isoformat()
        if commence_time_to:
            params["commenceTimeTo"] = commence_time_to.isoformat()

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, params=params)
            request_url = str(response.url)
            response.raise_for_status()
            raw = response.json()

        events: list[ProviderOddsEvent] = []
        for item in raw:
            home_team = item["home_team"]
            away_team = item["away_team"]
            bookmakers_parsed: list[ProviderBookmaker] = []

            for bk in item.get("bookmakers", []):
                markets_parsed: list[ProviderMarket] = []
                for mkt in bk.get("markets", []):
                    mkt_key = mkt["key"]
                    last_update = _parse_dt(mkt.get("last_update"))
                    outcomes_raw = mkt.get("outcomes", [])

                    if mkt_key == "h2h":
                        outcomes = [
                            ProviderOutcome(
                                name=o["name"],
                                price=float(o["price"]),
                            )
                            for o in outcomes_raw
                        ]
                        # Assign types
                        typed_outcomes = []
                        for o in outcomes_raw:
                            otype = _outcome_type_h2h(o["name"], home_team, away_team)
                            typed_outcomes.append(
                                ProviderOutcome(name=otype, price=float(o["price"]))
                            )
                        markets_parsed.append(
                            ProviderMarket(
                                key="h2h",
                                last_update=last_update,
                                outcomes=typed_outcomes,
                                line=None,
                            )
                        )
                    elif mkt_key == "totals":
                        # Group by line
                        line_groups: dict[float, list] = {}
                        for o in outcomes_raw:
                            line = _parse_totals_line(o.get("description", o["name"]))
                            if line is None:
                                line = _parse_totals_line(o["name"])
                            if line is None:
                                # try point field
                                line = float(o.get("point", 0)) if o.get("point") else None
                            if line is None:
                                continue
                            if line not in line_groups:
                                line_groups[line] = []
                            otype = _outcome_type_totals(o["name"])
                            line_groups[line].append(
                                ProviderOutcome(name=otype, price=float(o["price"]))
                            )

                        for line, outs in line_groups.items():
                            markets_parsed.append(
                                ProviderMarket(
                                    key="totals",
                                    last_update=last_update,
                                    outcomes=outs,
                                    line=line,
                                )
                            )

                bookmakers_parsed.append(
                    ProviderBookmaker(
                        key=bk["key"],
                        title=bk["title"],
                        markets=markets_parsed,
                    )
                )

            events.append(
                ProviderOddsEvent(
                    id=item["id"],
                    sport_key=item.get("sport_key", sport_key),
                    home_team=home_team,
                    away_team=away_team,
                    commence_time=_parse_dt(item.get("commence_time")),
                    bookmakers=bookmakers_parsed,
                )
            )

        return events, request_url, {"count": len(raw), "raw": raw}

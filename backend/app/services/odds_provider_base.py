from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ProviderEvent:
    id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: datetime


@dataclass
class ProviderOutcome:
    name: str
    price: float


@dataclass
class ProviderMarket:
    key: str  # h2h or totals
    last_update: Optional[datetime]
    outcomes: list[ProviderOutcome]
    line: Optional[float] = None


@dataclass
class ProviderBookmaker:
    key: str
    title: str
    markets: list[ProviderMarket]


@dataclass
class ProviderOddsEvent:
    id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: datetime
    bookmakers: list[ProviderBookmaker]


class OddsProvider(ABC):
    @abstractmethod
    async def fetch_events(self, sport_key: str, **kwargs) -> list[ProviderEvent]:
        ...

    @abstractmethod
    async def fetch_odds(
        self,
        sport_key: str,
        markets: list[str],
        regions: list[str] | None = None,
        bookmakers: list[str] | None = None,
        commence_time_from: datetime | None = None,
        commence_time_to: datetime | None = None,
    ) -> tuple[list[ProviderOddsEvent], str, dict]:
        """Returns (events, request_url, raw_response)"""
        ...

    # ── V2 rich endpoints (spec §13.2). Default implementations raise so that
    #    providers which do not support them fail clearly rather than silently;
    #    callers gate these behind ENABLE_RICH_ODDS_REFRESH. ──────────────────
    async def fetch_event_markets(self, sport_key: str, event_id: str, **kwargs) -> dict:
        """Discover available market keys for one event (quota_cost 0)."""
        raise NotImplementedError("fetch_event_markets not supported by this provider")

    async def fetch_event_odds(
        self,
        sport_key: str,
        event_id: str,
        markets: list[str],
        regions: list[str] | None = None,
        bookmakers: list[str] | None = None,
        **kwargs,
    ) -> tuple[ProviderOddsEvent | None, str, dict]:
        """Rich per-event odds across non-featured markets."""
        raise NotImplementedError("fetch_event_odds not supported by this provider")

    async def fetch_scores(
        self, sport_key: str, days_from: int | None = None, **kwargs
    ) -> tuple[list[dict], str, dict]:
        """Live / recently completed scores for backtesting."""
        raise NotImplementedError("fetch_scores not supported by this provider")

    async def fetch_historical_event_odds(
        self, sport_key: str, event_id: str, markets: list[str], snapshot: str, **kwargs
    ) -> tuple[dict, str, dict]:
        """Historical odds snapshot for an event (requires a paid plan)."""
        raise NotImplementedError("fetch_historical_event_odds not supported by this provider")

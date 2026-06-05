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

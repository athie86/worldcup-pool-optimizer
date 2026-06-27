from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class MarketOutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outcome_name: str
    outcome_type: str
    price_decimal: float
    implied_probability: Optional[float] = None
    normalized_probability: Optional[float] = None


class BookmakerMarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bookmaker_key: str
    bookmaker_title: str
    market_key: str
    last_update: Optional[datetime] = None
    line: Optional[float] = None
    market_outcomes: list[MarketOutcomeOut] = []


class OddsEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    odds_snapshot_id: uuid.UUID
    match_id: Optional[uuid.UUID] = None
    provider_event_id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: Optional[datetime] = None
    bookmaker_markets: list[BookmakerMarketOut] = []


class OddsSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    requested_markets: Optional[list[str]] = None
    requested_regions: Optional[list[str]] = None
    requested_bookmakers: Optional[list[str]] = None
    fetched_at: datetime
    status: Optional[str] = None
    request_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime


class MatchMarketOutcomeOut(BaseModel):
    outcome_type: str
    price_decimal: float
    normalized_probability: Optional[float] = None


class MatchBookmakerMarketOut(BaseModel):
    bookmaker_key: Optional[str] = None
    market_key: str
    line: Optional[float] = None
    outcomes: list[MatchMarketOutcomeOut] = []


class ConsensusProbabilitiesOut(BaseModel):
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    over_1_5: Optional[float] = None
    under_1_5: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    over_3_5: Optional[float] = None
    under_3_5: Optional[float] = None


class ManualOddsOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    market_key: str
    line: Optional[float] = None
    outcome_type: str
    price_decimal: float
    enabled: bool
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MatchOddsOut(BaseModel):
    """Aggregated odds for a single match, scoped to one snapshot (the latest
    by default). Drives the Odds & Overrides page."""

    match_id: uuid.UUID
    snapshot_id: Optional[uuid.UUID] = None
    fetched_at: Optional[datetime] = None
    bookmaker_markets: list[MatchBookmakerMarketOut] = []
    consensus_probabilities: ConsensusProbabilitiesOut = ConsensusProbabilitiesOut()
    overrides: list[ManualOddsOverrideOut] = []


class ManualOddsOverrideUpsert(BaseModel):
    market_key: str
    line: Optional[float] = None
    outcome_type: str
    price_decimal: float
    enabled: bool = True
    reason: Optional[str] = None


class OddsRefreshRequest(BaseModel):
    sport_key: Optional[str] = None
    markets: Optional[list[str]] = None
    regions: Optional[list[str]] = None
    bookmakers: Optional[list[str]] = None


class OddsRefreshResponse(BaseModel):
    snapshot_id: uuid.UUID
    status: str
    events_count: int
    message: Optional[str] = None

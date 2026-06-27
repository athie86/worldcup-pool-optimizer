from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fifa_code: Optional[str] = None
    name: str
    short_name: Optional[str] = None
    flag_emoji: Optional[str] = None
    group_label: Optional[str] = None


class TeamCreate(BaseModel):
    fifa_code: Optional[str] = None
    name: str
    short_name: Optional[str] = None
    flag_emoji: Optional[str] = None
    group_label: Optional[str] = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_event_id: Optional[str] = None
    match_number: Optional[int] = None
    stage: str
    group_label: Optional[str] = None
    home_team_id: Optional[uuid.UUID] = None
    away_team_id: Optional[uuid.UUID] = None
    home_team: Optional[TeamOut] = None
    away_team: Optional[TeamOut] = None
    home_placeholder: Optional[str] = None
    away_placeholder: Optional[str] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: str
    scoring_basis: str
    is_manual: bool
    is_complete_for_optimization: bool
    created_at: datetime
    updated_at: datetime


class MatchCreate(BaseModel):
    provider_event_id: Optional[str] = None
    match_number: Optional[int] = None
    stage: str
    group_label: Optional[str] = None
    home_team_id: Optional[uuid.UUID] = None
    away_team_id: Optional[uuid.UUID] = None
    home_placeholder: Optional[str] = None
    away_placeholder: Optional[str] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: str = "scheduled"
    scoring_basis: str = "ninety_minutes"
    is_manual: bool = False
    is_complete_for_optimization: bool = False


class MatchListItem(BaseModel):
    """Flattened match shape for list views (team names as plain strings)."""
    id: uuid.UUID
    provider_event_id: Optional[str] = None
    match_number: Optional[int] = None
    stage: str
    group_label: Optional[str] = None
    home_team_id: Optional[uuid.UUID] = None
    away_team_id: Optional[uuid.UUID] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_placeholder: Optional[str] = None
    away_placeholder: Optional[str] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: str
    scoring_basis: str
    is_manual: bool
    is_complete_for_optimization: bool
    has_overrides: bool = False
    has_odds: bool = False
    fit_status: Optional[str] = None


class PaginatedMatches(BaseModel):
    items: list[MatchListItem]
    total: int
    page: int
    page_size: int


class ImportSummary(BaseModel):
    message: str
    created: int = 0
    updated: int = 0
    teams_created: int = 0
    skipped: int = 0
    errors: list[str] = []


class DashboardStats(BaseModel):
    latest_odds_refresh: Optional[datetime] = None
    matches_ready: int = 0
    matches_incomplete: int = 0
    matches_with_overrides: int = 0
    latest_model_run: Optional[dict[str, Any]] = None
    avg_fit_quality: str = "pending"


class MatchUpdate(BaseModel):
    provider_event_id: Optional[str] = None
    match_number: Optional[int] = None
    stage: Optional[str] = None
    group_label: Optional[str] = None
    home_team_id: Optional[uuid.UUID] = None
    away_team_id: Optional[uuid.UUID] = None
    home_placeholder: Optional[str] = None
    away_placeholder: Optional[str] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: Optional[str] = None
    scoring_basis: Optional[str] = None
    is_manual: Optional[bool] = None
    is_complete_for_optimization: Optional[bool] = None

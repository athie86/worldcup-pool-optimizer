from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ScoringRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pool_config_id: uuid.UUID
    code: str
    label: str
    description: Optional[str] = None
    points: float
    enabled: bool
    display_specificity_rank: int
    phase: str = "group"
    example: Optional[str] = None
    config: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ScoringRuleCreate(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    points: float
    enabled: bool = True
    display_specificity_rank: int
    phase: str = "group"
    example: Optional[str] = None
    config: Optional[dict] = None


class ScoringRuleUpsert(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    points: float
    enabled: bool = True
    display_specificity_rank: int
    phase: str = "group"
    example: Optional[str] = None
    config: Optional[dict] = None


class ScoringRulePatch(BaseModel):
    """Partial update for a single scoring rule (points, enabled and/or config)."""
    points: Optional[float] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None


# Fields shared by the pool-config schemas. Combine modes are "best" | "additive".
class _PoolConfigBase(BaseModel):
    group_combine_mode: str = "best"
    knockout_combine_mode: str = "best"
    group_cap: Optional[float] = None
    knockout_cap: Optional[float] = None
    knockout_scoring_basis: str = "ninety_minutes"
    pick_lock_minutes_before: Optional[int] = None


class PoolConfigOut(_PoolConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    default_top_n: int
    candidate_max_goals: int
    ranking_metric: str
    margin_removal_method: str
    active: bool
    created_at: datetime
    updated_at: datetime
    scoring_rules: list[ScoringRuleOut] = []


class PoolConfigCreate(_PoolConfigBase):
    name: str
    description: Optional[str] = None
    default_top_n: int = 3
    candidate_max_goals: int = 5
    ranking_metric: str = "expected_points"
    margin_removal_method: str = "proportional"
    active: bool = False


class PoolConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_top_n: Optional[int] = None
    candidate_max_goals: Optional[int] = None
    ranking_metric: Optional[str] = None
    margin_removal_method: Optional[str] = None
    group_combine_mode: Optional[str] = None
    knockout_combine_mode: Optional[str] = None
    group_cap: Optional[float] = None
    knockout_cap: Optional[float] = None
    knockout_scoring_basis: Optional[str] = None
    pick_lock_minutes_before: Optional[int] = None
    active: Optional[bool] = None


class PoolConfigDuplicate(BaseModel):
    """Create a new pool config as a copy of an existing one (a saved preset)."""
    name: str
    description: Optional[str] = None
    active: bool = False

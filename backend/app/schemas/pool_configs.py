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
    created_at: datetime
    updated_at: datetime


class ScoringRuleCreate(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    points: float
    enabled: bool = True
    display_specificity_rank: int


class ScoringRuleUpsert(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    points: float
    enabled: bool = True
    display_specificity_rank: int


class ScoringRulePatch(BaseModel):
    """Partial update for a single scoring rule (points and/or enabled)."""
    points: Optional[float] = None
    enabled: Optional[bool] = None


class PoolConfigOut(BaseModel):
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


class PoolConfigCreate(BaseModel):
    name: str
    description: Optional[str] = None
    default_top_n: int = 3
    candidate_max_goals: int = 5
    ranking_metric: str = "expected_points"
    margin_removal_method: str = "proportional"
    active: bool = True


class PoolConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_top_n: Optional[int] = None
    candidate_max_goals: Optional[int] = None
    ranking_metric: Optional[str] = None
    margin_removal_method: Optional[str] = None
    active: Optional[bool] = None

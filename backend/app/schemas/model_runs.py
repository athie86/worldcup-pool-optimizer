from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class ScoreRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_model_fit_id: uuid.UUID
    predicted_home_goals: int
    predicted_away_goals: int
    rank: int
    expected_points: Optional[float] = None
    variance_points: Optional[float] = None
    zero_point_probability: Optional[float] = None
    score_probability: Optional[float] = None
    scoring_breakdown: Optional[dict] = None


class MatchModelFitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_run_id: uuid.UUID
    match_id: uuid.UUID
    lambda_home: Optional[float] = None
    lambda_away: Optional[float] = None
    fitted_home_win_prob: Optional[float] = None
    fitted_draw_prob: Optional[float] = None
    fitted_away_win_prob: Optional[float] = None
    market_home_win_prob: Optional[float] = None
    market_draw_prob: Optional[float] = None
    market_away_win_prob: Optional[float] = None
    fit_error: Optional[float] = None
    fit_status: Optional[str] = None
    diagnostics: Optional[dict] = None
    score_matrix: Optional[list] = None
    score_recommendations: list[ScoreRecommendationOut] = []


class ModelRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pool_config_id: Optional[uuid.UUID] = None
    odds_snapshot_id: Optional[uuid.UUID] = None
    run_type: str
    status: str
    parameters: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ModelRunCreate(BaseModel):
    pool_config_id: uuid.UUID
    odds_snapshot_id: Optional[uuid.UUID] = None
    run_type: str = "manual"
    parameters: Optional[dict] = None


class ModelRunWithFits(ModelRunOut):
    match_model_fits: list[MatchModelFitOut] = []


class DiagnosticsRow(BaseModel):
    target: str
    market: float
    model: float
    error: float


class DiagnosticsOut(BaseModel):
    match_id: uuid.UUID
    lambda_home: float
    lambda_away: float
    total_expected_goals: float
    rmse: float
    fit_status: str
    rows: list[DiagnosticsRow]
    warnings: list[str]
    score_matrix: list[list[float]]

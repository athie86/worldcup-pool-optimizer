import uuid
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    username: Mapped[str] = mapped_column(Text, unique=True, default="admin")
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    fifa_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flag_emoji: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    home_matches: Mapped[list["Match"]] = relationship("Match", foreign_keys="Match.home_team_id", back_populates="home_team")
    away_matches: Mapped[list["Match"]] = relationship("Match", foreign_keys="Match.away_team_id", back_populates="away_team")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    provider_event_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    group_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    home_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    away_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    home_placeholder: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    away_placeholder: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kickoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="scheduled")
    scoring_basis: Mapped[str] = mapped_column(Text, default="ninety_minutes")
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    is_complete_for_optimization: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    home_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[home_team_id], back_populates="home_matches")
    away_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[away_team_id], back_populates="away_matches")
    odds_events: Mapped[list["OddsEvent"]] = relationship("OddsEvent", back_populates="match")
    model_fits: Mapped[list["MatchModelFit"]] = relationship("MatchModelFit", back_populates="match")
    manual_overrides: Mapped[list["ManualOddsOverride"]] = relationship("ManualOddsOverride", back_populates="match", cascade="all, delete-orphan")


class PoolConfig(Base):
    __tablename__ = "pool_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_top_n: Mapped[int] = mapped_column(Integer, default=3)
    candidate_max_goals: Mapped[int] = mapped_column(Integer, default=5)
    ranking_metric: Mapped[str] = mapped_column(Text, default="expected_points")
    margin_removal_method: Mapped[str] = mapped_column(Text, default="proportional")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    scoring_rules: Mapped[list["ScoringRule"]] = relationship("ScoringRule", back_populates="pool_config", cascade="all, delete-orphan")
    model_runs: Mapped[list["ModelRun"]] = relationship("ModelRun", back_populates="pool_config")


class ScoringRule(Base):
    __tablename__ = "scoring_rules"
    __table_args__ = (
        UniqueConstraint("pool_config_id", "code", name="uq_scoring_rules_config_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    pool_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pool_configs.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    points: Mapped[float] = mapped_column(Numeric(8, 3))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_specificity_rank: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pool_config: Mapped["PoolConfig"] = relationship("PoolConfig", back_populates="scoring_rules")


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    provider: Mapped[str] = mapped_column(Text)
    requested_markets: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    requested_regions: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    requested_bookmakers: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    odds_events: Mapped[list["OddsEvent"]] = relationship("OddsEvent", back_populates="odds_snapshot", cascade="all, delete-orphan")
    model_runs: Mapped[list["ModelRun"]] = relationship("ModelRun", back_populates="odds_snapshot")


class OddsEvent(Base):
    __tablename__ = "odds_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    odds_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("odds_snapshots.id", ondelete="CASCADE"))
    match_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=True)
    provider_event_id: Mapped[str] = mapped_column(Text)
    sport_key: Mapped[str] = mapped_column(Text)
    home_team: Mapped[str] = mapped_column(Text)
    away_team: Mapped[str] = mapped_column(Text)
    commence_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    odds_snapshot: Mapped["OddsSnapshot"] = relationship("OddsSnapshot", back_populates="odds_events")
    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="odds_events")
    bookmaker_markets: Mapped[list["BookmakerMarket"]] = relationship("BookmakerMarket", back_populates="odds_event", cascade="all, delete-orphan")


class BookmakerMarket(Base):
    __tablename__ = "bookmaker_markets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    odds_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("odds_events.id", ondelete="CASCADE"))
    bookmaker_key: Mapped[str] = mapped_column(Text)
    bookmaker_title: Mapped[str] = mapped_column(Text)
    market_key: Mapped[str] = mapped_column(Text)
    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    line: Mapped[Optional[float]] = mapped_column(Numeric(8, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    odds_event: Mapped["OddsEvent"] = relationship("OddsEvent", back_populates="bookmaker_markets")
    market_outcomes: Mapped[list["MarketOutcome"]] = relationship("MarketOutcome", back_populates="bookmaker_market", cascade="all, delete-orphan")


class MarketOutcome(Base):
    __tablename__ = "market_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    bookmaker_market_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookmaker_markets.id", ondelete="CASCADE"))
    outcome_name: Mapped[str] = mapped_column(Text)
    outcome_type: Mapped[str] = mapped_column(Text)
    price_decimal: Mapped[float] = mapped_column(Numeric(12, 6))
    implied_probability: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    normalized_probability: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bookmaker_market: Mapped["BookmakerMarket"] = relationship("BookmakerMarket", back_populates="market_outcomes")


class ManualOddsOverride(Base):
    __tablename__ = "manual_odds_overrides"
    __table_args__ = (
        UniqueConstraint("match_id", "market_key", "line", "outcome_type", name="uq_manual_odds_override"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"))
    market_key: Mapped[str] = mapped_column(Text)
    line: Mapped[Optional[float]] = mapped_column(Numeric(8, 3), nullable=True)
    outcome_type: Mapped[str] = mapped_column(Text)
    price_decimal: Mapped[float] = mapped_column(Numeric(12, 6))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    match: Mapped["Match"] = relationship("Match", back_populates="manual_overrides")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    pool_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("pool_configs.id"), nullable=True)
    odds_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("odds_snapshots.id"), nullable=True)
    run_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    parameters: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pool_config: Mapped[Optional["PoolConfig"]] = relationship("PoolConfig", back_populates="model_runs")
    odds_snapshot: Mapped[Optional["OddsSnapshot"]] = relationship("OddsSnapshot", back_populates="model_runs")
    match_model_fits: Mapped[list["MatchModelFit"]] = relationship("MatchModelFit", back_populates="model_run", cascade="all, delete-orphan")
    exports: Mapped[list["Export"]] = relationship("Export", back_populates="model_run")


class MatchModelFit(Base):
    __tablename__ = "match_model_fits"
    __table_args__ = (
        UniqueConstraint("model_run_id", "match_id", name="uq_match_model_fit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    model_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="CASCADE"))
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id"))
    lambda_home: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    lambda_away: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    fitted_home_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    fitted_draw_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    fitted_away_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    market_home_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    market_draw_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    market_away_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    fit_error: Mapped[Optional[float]] = mapped_column(Numeric(14, 10), nullable=True)
    fit_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnostics: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    score_matrix: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    model_run: Mapped["ModelRun"] = relationship("ModelRun", back_populates="match_model_fits")
    match: Mapped["Match"] = relationship("Match", back_populates="model_fits")
    score_recommendations: Mapped[list["ScoreRecommendation"]] = relationship("ScoreRecommendation", back_populates="match_model_fit", cascade="all, delete-orphan")


class ScoreRecommendation(Base):
    __tablename__ = "score_recommendations"
    __table_args__ = (
        UniqueConstraint("match_model_fit_id", "rank", name="uq_score_recommendation_rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    match_model_fit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("match_model_fits.id", ondelete="CASCADE"))
    predicted_home_goals: Mapped[int] = mapped_column(Integer)
    predicted_away_goals: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    expected_points: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    variance_points: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    zero_point_probability: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    score_probability: Mapped[Optional[float]] = mapped_column(Numeric(12, 9), nullable=True)
    scoring_breakdown: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match_model_fit: Mapped["MatchModelFit"] = relationship("MatchModelFit", back_populates="score_recommendations")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    model_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id"), nullable=True)
    export_type: Mapped[str] = mapped_column(Text)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    model_run: Mapped[Optional["ModelRun"]] = relationship("ModelRun", back_populates="exports")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    job_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

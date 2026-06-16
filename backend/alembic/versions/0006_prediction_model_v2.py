"""Prediction model V2 storage: richer markets, v2 fit fields, constraints table.

Additive and guarded (spec WCPO-PRED-MODEL-V2 §12). All new columns are
nullable so existing v1 rows read unchanged, and the upgrade checks for
existing columns/tables so it is safe to re-run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _drop(table: str, name: str) -> None:
    if name in _columns(table):
        op.drop_column(table, name)


def upgrade():
    JSONB = postgresql.JSONB

    # ── bookmaker_markets (§12.1) ───────────────────────────────────────────
    _add("bookmaker_markets", sa.Column("period", sa.Text(), nullable=True))
    _add("bookmaker_markets", sa.Column("is_live", sa.Boolean(), nullable=True))
    _add("bookmaker_markets", sa.Column("source_market_key", sa.Text(), nullable=True))
    _add("bookmaker_markets", sa.Column("market_metadata", JSONB(), nullable=True))

    # ── market_outcomes (§12.2) ─────────────────────────────────────────────
    _add("market_outcomes", sa.Column("point", sa.Numeric(8, 3), nullable=True))
    _add("market_outcomes", sa.Column("description", sa.Text(), nullable=True))
    _add("market_outcomes", sa.Column("bet_limit", sa.Numeric(14, 2), nullable=True))
    _add("market_outcomes", sa.Column("link", sa.Text(), nullable=True))
    _add("market_outcomes", sa.Column("sid", sa.Text(), nullable=True))
    _add("market_outcomes", sa.Column("raw_outcome", JSONB(), nullable=True))

    # ── match_model_fits (§12.4) ────────────────────────────────────────────
    mmf_cols = [
        sa.Column("model_type", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("fit_tier", sa.Text(), nullable=True),
        sa.Column("prior_lambda_home", sa.Numeric(12, 8), nullable=True),
        sa.Column("prior_lambda_away", sa.Numeric(12, 8), nullable=True),
        sa.Column("prior_rho", sa.Numeric(12, 8), nullable=True),
        sa.Column("final_home_xg", sa.Numeric(12, 8), nullable=True),
        sa.Column("final_away_xg", sa.Numeric(12, 8), nullable=True),
        sa.Column("final_total_xg", sa.Numeric(12, 8), nullable=True),
        sa.Column("prior_error", sa.Numeric(14, 10), nullable=True),
        sa.Column("calibrated_error", sa.Numeric(14, 10), nullable=True),
        sa.Column("max_constraint_error", sa.Numeric(14, 10), nullable=True),
        sa.Column("constraint_count", sa.Integer(), nullable=True),
        sa.Column("market_coverage_score", sa.Numeric(12, 8), nullable=True),
        sa.Column("actual_score_max", sa.Integer(), nullable=True),
        sa.Column("candidate_score_max", sa.Integer(), nullable=True),
        sa.Column("tail_mass", sa.Numeric(14, 10), nullable=True),
        sa.Column("used_markets", JSONB(), nullable=True),
        sa.Column("market_constraints_json", JSONB(), nullable=True),
        sa.Column("prior_score_matrix", JSONB(), nullable=True),
        sa.Column("calibration_parameters", JSONB(), nullable=True),
    ]
    for col in mmf_cols:
        _add("match_model_fits", col)

    # ── market_constraints table (§12.3) ────────────────────────────────────
    if "market_constraints" not in _tables():
        op.create_table(
            "market_constraints",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("odds_snapshot_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("odds_snapshots.id", ondelete="CASCADE"), nullable=True),
            sa.Column("odds_event_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("odds_events.id", ondelete="CASCADE"), nullable=True),
            sa.Column("match_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("matches.id"), nullable=True),
            sa.Column("market_key", sa.Text(), nullable=False),
            sa.Column("market_family", sa.Text(), nullable=False),
            sa.Column("constraint_type", sa.Text(), nullable=False),
            sa.Column("side", sa.Text(), nullable=True),
            sa.Column("line", sa.Numeric(8, 3), nullable=True),
            sa.Column("target_type", sa.Text(), nullable=False),
            sa.Column("target_value", sa.Numeric(14, 10), nullable=False),
            sa.Column("weight", sa.Numeric(14, 10), nullable=False),
            sa.Column("devig_method", sa.Text(), nullable=False),
            sa.Column("consensus_method", sa.Text(), nullable=False,
                      server_default="weighted_average"),
            sa.Column("bookmaker_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("excluded_bookmaker_count", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("freshness_minutes", sa.Numeric(12, 4), nullable=True),
            sa.Column("quality_score", sa.Numeric(12, 8), nullable=True),
            sa.Column("source_details", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_market_constraints_match_id", "market_constraints", ["match_id"])
        op.create_index("ix_market_constraints_odds_snapshot_id", "market_constraints",
                        ["odds_snapshot_id"])
        op.create_index("ix_market_constraints_market_family", "market_constraints",
                        ["market_family"])

    # ── supporting indexes ──────────────────────────────────────────────────
    existing_idx = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("bookmaker_markets")}
    if "ix_bookmaker_markets_market_key" not in existing_idx:
        op.create_index("ix_bookmaker_markets_market_key", "bookmaker_markets", ["market_key"])
    mo_idx = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("market_outcomes")}
    if "ix_market_outcomes_outcome_type" not in mo_idx:
        op.create_index("ix_market_outcomes_outcome_type", "market_outcomes", ["outcome_type"])


def downgrade():
    for name in ("ix_market_outcomes_outcome_type",):
        try:
            op.drop_index(name, table_name="market_outcomes")
        except Exception:
            pass
    try:
        op.drop_index("ix_bookmaker_markets_market_key", table_name="bookmaker_markets")
    except Exception:
        pass

    if "market_constraints" in _tables():
        op.drop_table("market_constraints")

    for name in (
        "model_type", "model_version", "fit_tier", "prior_lambda_home",
        "prior_lambda_away", "prior_rho", "final_home_xg", "final_away_xg",
        "final_total_xg", "prior_error", "calibrated_error", "max_constraint_error",
        "constraint_count", "market_coverage_score", "actual_score_max",
        "candidate_score_max", "tail_mass", "used_markets",
        "market_constraints_json", "prior_score_matrix", "calibration_parameters",
    ):
        _drop("match_model_fits", name)

    for name in ("point", "description", "bet_limit", "link", "sid", "raw_outcome"):
        _drop("market_outcomes", name)

    for name in ("period", "is_live", "source_market_key", "market_metadata"):
        _drop("bookmaker_markets", name)

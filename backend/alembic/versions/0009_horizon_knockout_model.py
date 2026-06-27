"""Horizon-consistent knockout model: additive columns.

Adds nullable columns to ``match_model_fits`` (the full horizon surfaces +
terminal probabilities + horizon diagnostics) and ``score_recommendations``
(per-recommendation basis/horizon context + terminal probabilities). Everything
is additive and nullable, so existing rows and the V2 pipeline are unaffected.

Defensive/idempotent like the other migrations: each column is added only when
it is not already present, so this is safe on a fresh DB whose schema came from
the live ORM metadata.

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


_JSONB = postgresql.JSONB(astext_type=sa.Text())

_MATCH_MODEL_FIT_NEW = {
    "score_matrix_90": sa.Column("score_matrix_90", _JSONB, nullable=True),
    "score_matrix_120": sa.Column("score_matrix_120", _JSONB, nullable=True),
    "terminal_states": sa.Column("terminal_states", _JSONB, nullable=True),
    "p_goes_to_extra_time": sa.Column("p_goes_to_extra_time", sa.Float(), nullable=True),
    "p_goes_to_penalties": sa.Column("p_goes_to_penalties", sa.Float(), nullable=True),
    "p_home_advances": sa.Column("p_home_advances", sa.Float(), nullable=True),
    "p_away_advances": sa.Column("p_away_advances", sa.Float(), nullable=True),
    "p_home_wins_penalties_given_pens": sa.Column(
        "p_home_wins_penalties_given_pens", sa.Float(), nullable=True),
    "p_away_wins_penalties_given_pens": sa.Column(
        "p_away_wins_penalties_given_pens", sa.Float(), nullable=True),
    "horizon_model_type": sa.Column("horizon_model_type", sa.Text(), nullable=True),
    "horizon_model_version": sa.Column("horizon_model_version", sa.Text(), nullable=True),
    "horizon_fit_tier": sa.Column("horizon_fit_tier", sa.Text(), nullable=True),
    "horizon_diagnostics": sa.Column("horizon_diagnostics", _JSONB, nullable=True),
}

_SCORE_RECOMMENDATION_NEW = {
    "scoring_basis": sa.Column("scoring_basis", sa.Text(), nullable=True),
    "score_horizon": sa.Column("score_horizon", sa.Text(), nullable=True),
    "outcome_horizon": sa.Column("outcome_horizon", sa.Text(), nullable=True),
    "predicted_penalty_winner": sa.Column("predicted_penalty_winner", sa.Text(), nullable=True),
    "predicted_advancer": sa.Column("predicted_advancer", sa.Text(), nullable=True),
    "expected_points_by_state": sa.Column("expected_points_by_state", _JSONB, nullable=True),
    "expected_points_by_rule": sa.Column("expected_points_by_rule", _JSONB, nullable=True),
    "prob_exact_90": sa.Column("prob_exact_90", sa.Float(), nullable=True),
    "prob_exact_120": sa.Column("prob_exact_120", sa.Float(), nullable=True),
    "prob_home_advances": sa.Column("prob_home_advances", sa.Float(), nullable=True),
    "prob_away_advances": sa.Column("prob_away_advances", sa.Float(), nullable=True),
    "prob_goes_to_penalties": sa.Column("prob_goes_to_penalties", sa.Float(), nullable=True),
}


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    fit_cols = _columns("match_model_fits")
    for name, column in _MATCH_MODEL_FIT_NEW.items():
        if name not in fit_cols:
            op.add_column("match_model_fits", column)

    rec_cols = _columns("score_recommendations")
    for name, column in _SCORE_RECOMMENDATION_NEW.items():
        if name not in rec_cols:
            op.add_column("score_recommendations", column)

    # Backfill: existing fits' score_matrix becomes both the 90' and 120' surface
    # (non-knockout / legacy rows have no extra-time distinction).
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE match_model_fits "
        "SET score_matrix_90 = score_matrix "
        "WHERE score_matrix_90 IS NULL AND score_matrix IS NOT NULL"
    ))
    bind.execute(sa.text(
        "UPDATE match_model_fits "
        "SET score_matrix_120 = score_matrix "
        "WHERE score_matrix_120 IS NULL AND score_matrix IS NOT NULL"
    ))


def downgrade() -> None:
    for name in reversed(list(_SCORE_RECOMMENDATION_NEW)):
        if name in _columns("score_recommendations"):
            op.drop_column("score_recommendations", name)
    for name in reversed(list(_MATCH_MODEL_FIT_NEW)):
        if name in _columns("match_model_fits"):
            op.drop_column("match_model_fits", name)

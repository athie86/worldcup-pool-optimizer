"""add scoring_mode and binary points to pool_configs

Adds the columns backing the binary scoring mode. Existing rows default to the
standard rule-based scoring with 1 point each for a correct result and correct
total goals, so behaviour is unchanged until a config is switched to binary.

This migration is idempotent: the baseline ``0001`` migration builds the schema
from the live ORM metadata (which already includes these columns), so on a fresh
database the columns may already exist. We therefore only add the ones that are
missing, which also makes the migration safe to run against databases that were
originally created by the app's ``create_all`` startup path.

Revision ID: 0002_pool_config_scoring_mode
Revises: 0001_initial_schema
Create Date: 2026-06-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_pool_config_scoring_mode"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


_NEW_COLUMNS = {
    "scoring_mode": sa.Column("scoring_mode", sa.Text(), nullable=False, server_default="standard"),
    "binary_result_points": sa.Column("binary_result_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
    "binary_total_goals_points": sa.Column("binary_total_goals_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
}


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns("pool_configs")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, column in _NEW_COLUMNS.items():
        if name not in existing:
            op.add_column("pool_configs", column)


def downgrade() -> None:
    existing = _existing_columns()
    for name in reversed(list(_NEW_COLUMNS)):
        if name in existing:
            op.drop_column("pool_configs", name)

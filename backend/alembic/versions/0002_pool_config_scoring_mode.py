"""add scoring_mode and binary points to pool_configs

Adds the columns backing the binary scoring mode. Existing rows default to the
standard rule-based scoring with 1 point each for a correct result and correct
total goals, so behaviour is unchanged until a config is switched to binary.

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


def upgrade() -> None:
    op.add_column(
        "pool_configs",
        sa.Column("scoring_mode", sa.Text(), nullable=False, server_default="standard"),
    )
    op.add_column(
        "pool_configs",
        sa.Column("binary_result_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
    )
    op.add_column(
        "pool_configs",
        sa.Column("binary_total_goals_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("pool_configs", "binary_total_goals_points")
    op.drop_column("pool_configs", "binary_result_points")
    op.drop_column("pool_configs", "scoring_mode")

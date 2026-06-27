"""Knockout scoring support: phase column on scoring_rules, penalties_winner on recommendations.

Adds:
- scoring_rules.phase (TEXT, default 'group') — separates group vs knockout rule sets
- Replaces UNIQUE(pool_config_id, code) with UNIQUE(pool_config_id, code, phase)
- score_recommendations.penalties_winner (TEXT, nullable) — optimizer's recommended penalty winner
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _constraints(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_unique_constraints(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade():
    # Add phase column to scoring_rules (existing rows default to 'group')
    _add(
        "scoring_rules",
        sa.Column("phase", sa.Text(), nullable=False, server_default="group"),
    )

    # Replace the unique constraint to include phase
    existing = _constraints("scoring_rules")
    if "uq_scoring_rules_config_code" in existing:
        op.drop_constraint(
            "uq_scoring_rules_config_code",
            "scoring_rules",
            type_="unique",
        )
    if "uq_scoring_rules_config_code_phase" not in existing:
        op.create_unique_constraint(
            "uq_scoring_rules_config_code_phase",
            "scoring_rules",
            ["pool_config_id", "code", "phase"],
        )

    # Add penalties_winner to score_recommendations
    _add(
        "score_recommendations",
        sa.Column("penalties_winner", sa.Text(), nullable=True),
    )


def downgrade():
    cols = _columns("score_recommendations")
    if "penalties_winner" in cols:
        op.drop_column("score_recommendations", "penalties_winner")

    existing = _constraints("scoring_rules")
    if "uq_scoring_rules_config_code_phase" in existing:
        op.drop_constraint(
            "uq_scoring_rules_config_code_phase",
            "scoring_rules",
            type_="unique",
        )
    if "uq_scoring_rules_config_code" not in existing:
        op.create_unique_constraint(
            "uq_scoring_rules_config_code",
            "scoring_rules",
            ["pool_config_id", "code"],
        )

    cols = _columns("scoring_rules")
    if "phase" in cols:
        op.drop_column("scoring_rules", "phase")

"""Drop unused users and job_runs tables.

This migration is guarded: the baseline ``0001`` migration builds the schema
from live ORM metadata, which no longer includes these models, so on a fresh
database the tables never exist. Only databases created before the models were
removed will actually have them.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004_winner_only"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade():
    existing = _existing_tables()
    if "job_runs" in existing:
        op.drop_table("job_runs")
    if "users" in existing:
        op.drop_table("users")


def downgrade():
    existing = _existing_tables()
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("username", sa.Text(), unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "job_runs" not in existing:
        op.create_table(
            "job_runs",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("job_name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("details", sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )

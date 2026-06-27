"""initial schema

Creates all tables from the SQLAlchemy models. This project previously shipped
without any migration versions, which meant ``alembic upgrade head`` did not
create the schema. This baseline migration builds every table directly from the
ORM metadata so the documented setup flow works on a fresh database.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-06
"""
from __future__ import annotations

from alembic import op

# Import the metadata that describes every table.
from app.db.base import Base
from app.db import models  # noqa: F401 - ensure all models are registered


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # checkfirst=True keeps this safe if some tables were already created
    # (e.g. by the app's startup create_all).
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

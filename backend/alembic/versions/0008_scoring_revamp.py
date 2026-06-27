"""Scoring system revamp: unified component model + four seeded presets.

Replaces the old "standard rule table vs binary mode" split with one model:

* ``pool_configs`` gains per-phase combine modes (``best`` | ``additive``),
  optional per-match caps, a knockout scoring basis, and an informational
  pick-lock field. The binary columns (``scoring_mode``,
  ``binary_result_points``, ``binary_total_goals_points``) are dropped.
* ``scoring_rules`` gains ``example`` (worked example for the UI) and ``config``
  (component options, e.g. total-goals bucketing).
* All existing pool configs and scoring rules are **wiped** and replaced with the
  four seeded presets defined in ``app.core.defaults`` (none active by default).

Defensive/idempotent like the other migrations: columns are added/dropped only
when (not) present, so this is safe on a fresh DB whose schema came from the live
ORM metadata.

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.defaults import SEED_PRESETS, build_preset_rules

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


# New columns on pool_configs (name -> Column).
_POOL_CONFIG_NEW = {
    "group_combine_mode": sa.Column("group_combine_mode", sa.Text(), nullable=False, server_default="best"),
    "knockout_combine_mode": sa.Column("knockout_combine_mode", sa.Text(), nullable=False, server_default="best"),
    "group_cap": sa.Column("group_cap", sa.Numeric(8, 3), nullable=True),
    "knockout_cap": sa.Column("knockout_cap", sa.Numeric(8, 3), nullable=True),
    "knockout_scoring_basis": sa.Column(
        "knockout_scoring_basis", sa.Text(), nullable=False, server_default="ninety_minutes"
    ),
    "pick_lock_minutes_before": sa.Column("pick_lock_minutes_before", sa.Integer(), nullable=True),
}

# Old binary columns to drop on upgrade (and re-add on downgrade).
_POOL_CONFIG_OLD = {
    "scoring_mode": sa.Column("scoring_mode", sa.Text(), nullable=False, server_default="standard"),
    "binary_result_points": sa.Column("binary_result_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
    "binary_total_goals_points": sa.Column("binary_total_goals_points", sa.Numeric(8, 3), nullable=False, server_default="1"),
}

_SCORING_RULE_NEW = {
    "example": sa.Column("example", sa.Text(), nullable=True),
    "config": sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
}


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


# Lightweight table handles for data DML.
_pool_configs = sa.table(
    "pool_configs",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    sa.column("default_top_n", sa.Integer),
    sa.column("candidate_max_goals", sa.Integer),
    sa.column("ranking_metric", sa.Text),
    sa.column("margin_removal_method", sa.Text),
    sa.column("group_combine_mode", sa.Text),
    sa.column("knockout_combine_mode", sa.Text),
    sa.column("group_cap", sa.Numeric(8, 3)),
    sa.column("knockout_cap", sa.Numeric(8, 3)),
    sa.column("knockout_scoring_basis", sa.Text),
    sa.column("pick_lock_minutes_before", sa.Integer),
    sa.column("active", sa.Boolean),
)

_scoring_rules = sa.table(
    "scoring_rules",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("pool_config_id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.Text),
    sa.column("label", sa.Text),
    sa.column("description", sa.Text),
    sa.column("points", sa.Numeric(8, 3)),
    sa.column("enabled", sa.Boolean),
    sa.column("display_specificity_rank", sa.Integer),
    sa.column("phase", sa.Text),
    sa.column("example", sa.Text),
    sa.column("config", postgresql.JSONB(astext_type=sa.Text())),
)


def _seed_presets() -> None:
    """Insert the four seeded presets and their scoring rules (none active)."""
    for preset in SEED_PRESETS:
        config_id = uuid.uuid4()
        op.bulk_insert(_pool_configs, [{
            "id": config_id,
            "name": preset["name"],
            "description": preset.get("description"),
            "default_top_n": 3,
            "candidate_max_goals": 5,
            "ranking_metric": "expected_points",
            "margin_removal_method": "proportional",
            "group_combine_mode": preset["group_combine_mode"],
            "knockout_combine_mode": preset["knockout_combine_mode"],
            "group_cap": preset["group_cap"],
            "knockout_cap": preset["knockout_cap"],
            "knockout_scoring_basis": preset["knockout_scoring_basis"],
            "pick_lock_minutes_before": preset["pick_lock_minutes_before"],
            "active": False,
        }])
        rows = []
        for r in build_preset_rules(preset):
            rows.append({
                "id": uuid.uuid4(),
                "pool_config_id": config_id,
                "code": r["code"],
                "label": r["label"],
                "description": r.get("description"),
                "points": r["points"],
                "enabled": r["enabled"],
                "display_specificity_rank": r["display_specificity_rank"],
                "phase": r["phase"],
                "example": r.get("example"),
                "config": r.get("config"),
            })
        op.bulk_insert(_scoring_rules, rows)


def upgrade() -> None:
    # 1. Schema: add new columns, drop old binary columns.
    pc_cols = _columns("pool_configs")
    for name, column in _POOL_CONFIG_NEW.items():
        if name not in pc_cols:
            op.add_column("pool_configs", column)
    for name in _SCORING_RULE_NEW:
        if name not in _columns("scoring_rules"):
            op.add_column("scoring_rules", _SCORING_RULE_NEW[name])
    for name in _POOL_CONFIG_OLD:
        if name in pc_cols:
            op.drop_column("pool_configs", name)

    # 2. Wipe existing scoring data. Detach model_runs first (they FK to
    # pool_configs without cascade), then delete rules and configs.
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE model_runs SET pool_config_id = NULL"))
    bind.execute(sa.text("DELETE FROM scoring_rules"))
    bind.execute(sa.text("DELETE FROM pool_configs"))

    # 3. Seed the four presets.
    _seed_presets()


def downgrade() -> None:
    # Re-add the old binary columns; drop the new ones. Seeded data is not
    # restored (the previous rows were destroyed on upgrade).
    pc_cols = _columns("pool_configs")
    for name, column in _POOL_CONFIG_OLD.items():
        if name not in pc_cols:
            op.add_column("pool_configs", column)
    for name in reversed(list(_SCORING_RULE_NEW)):
        if name in _columns("scoring_rules"):
            op.drop_column("scoring_rules", name)
    for name in reversed(list(_POOL_CONFIG_NEW)):
        if name in _columns("pool_configs"):
            op.drop_column("pool_configs", name)

"""add correct_winner_only scoring rule

Backfills the new ``correct_winner_only`` rule (correct winner but wrong goals
for both teams — no exact score and neither team's goal count matches) into
existing pool configurations. New configs already receive it via the default
rule set.

For each pool config that does not already have the rule, the existing rules
with ``display_specificity_rank`` >= 5 are shifted down by one to make room, and
the new rule is inserted at rank 5 (just below "Correct Winner + Any Team's
Goals"). The insert is keyed on the ``(pool_config_id, code)`` unique
constraint, so the migration is idempotent.

NOTE: the revision id is kept short (<= 32 chars) because Alembic's
``alembic_version.version_num`` column is ``varchar(32)``; a longer id breaks
``alembic upgrade head``.

Revision ID: 0004_winner_only
Revises: 0003_winner_any_team_goals
Create Date: 2026-06-08
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_winner_only"
down_revision = "0003_winner_any_team_goals"
branch_labels = None
depends_on = None

_RULE_CODE = "correct_winner_only"
_RULE = {
    "code": _RULE_CODE,
    "label": "Correct Winner Only",
    "description": "Correct winner but wrong goals for both teams (no exact score, neither team's goals match)",
    "points": 3.0,
    "enabled": True,
    "display_specificity_rank": 5,
}


def upgrade() -> None:
    bind = op.get_bind()

    # Pool configs that don't yet have the rule.
    config_ids = bind.execute(
        sa.text(
            """
            SELECT pc.id
            FROM pool_configs pc
            WHERE NOT EXISTS (
                SELECT 1 FROM scoring_rules sr
                WHERE sr.pool_config_id = pc.id AND sr.code = :code
            )
            """
        ),
        {"code": _RULE_CODE},
    ).fetchall()

    for (config_id,) in config_ids:
        # Make room: shift everything at or below the new rule's rank.
        bind.execute(
            sa.text(
                """
                UPDATE scoring_rules
                SET display_specificity_rank = display_specificity_rank + 1
                WHERE pool_config_id = :pid AND display_specificity_rank >= :rank
                """
            ),
            {"pid": config_id, "rank": _RULE["display_specificity_rank"]},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO scoring_rules
                    (id, pool_config_id, code, label, description, points,
                     enabled, display_specificity_rank)
                VALUES
                    (:id, :pid, :code, :label, :description, :points,
                     :enabled, :rank)
                """
            ),
            {
                "id": uuid.uuid4(),
                "pid": config_id,
                "code": _RULE["code"],
                "label": _RULE["label"],
                "description": _RULE["description"],
                "points": _RULE["points"],
                "enabled": _RULE["enabled"],
                "rank": _RULE["display_specificity_rank"],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()

    config_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT pool_config_id
            FROM scoring_rules
            WHERE code = :code
            """
        ),
        {"code": _RULE_CODE},
    ).fetchall()

    bind.execute(
        sa.text("DELETE FROM scoring_rules WHERE code = :code"),
        {"code": _RULE_CODE},
    )

    for (config_id,) in config_ids:
        # Reverse the rank shift applied in upgrade().
        bind.execute(
            sa.text(
                """
                UPDATE scoring_rules
                SET display_specificity_rank = display_specificity_rank - 1
                WHERE pool_config_id = :pid AND display_specificity_rank > :rank
                """
            ),
            {"pid": config_id, "rank": _RULE["display_specificity_rank"]},
        )

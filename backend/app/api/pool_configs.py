from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.pool_configs import (
    PoolConfigOut,
    PoolConfigCreate,
    PoolConfigUpdate,
    PoolConfigDuplicate,
    ScoringRuleUpsert,
    ScoringRulePatch,
    ScoringRuleOut,
)
from ..core.defaults import get_default_rules
from ..services.horizon import (
    RULE_DEFINITIONS,
    rule_is_valid_for_basis,
    validate_pool_config_scoring_consistency,
)
from .deps import get_current_user

router = APIRouter()


def _reconcile_rules_for_basis(rule_dicts: list[dict], basis: str) -> list[dict]:
    """Disable knockout rules a basis cannot support, so a seed is always valid.

    Group-phase rules are untouched. Knockout bonus rules (advance /
    penalty_winner) are forced disabled when the basis does not allow them.
    """
    for rd in rule_dicts:
        if rd.get("phase") != "knockout":
            continue
        code = rd.get("code")
        if code in RULE_DEFINITIONS and not rule_is_valid_for_basis(code, "knockout", basis):
            rd["enabled"] = False
    return rule_dicts


async def _ensure_default_rules(
    db: AsyncSession, config_id: uuid.UUID, basis: str = "ninety_minutes"
) -> None:
    """Seed the canonical default scoring rules for a config that has none.

    The seed is reconciled to ``basis`` so a brand-new config is never created in
    an inconsistent rule/basis state.
    """
    for rule_data in _reconcile_rules_for_basis(get_default_rules(), basis):
        db.add(models.ScoringRule(pool_config_id=config_id, **rule_data))


def _assert_consistent(basis: str, rules: list) -> None:
    """Raise 400 if the enabled knockout rules are inconsistent with the basis."""
    errors = validate_pool_config_scoring_consistency(basis, rules)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))


async def _load_rules(db: AsyncSession, config_id: uuid.UUID) -> list[models.ScoringRule]:
    result = await db.execute(
        select(models.ScoringRule)
        .where(models.ScoringRule.pool_config_id == config_id)
        .order_by(models.ScoringRule.display_specificity_rank.asc())
    )
    return list(result.scalars().all())


@router.get("", response_model=list[PoolConfigOut])
async def list_pool_configs(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .order_by(models.PoolConfig.created_at.asc())
    )
    return result.scalars().all()


@router.post("", response_model=PoolConfigOut, status_code=201)
async def create_pool_config(
    body: PoolConfigCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    config = models.PoolConfig(**body.model_dump())
    db.add(config)
    await db.flush()

    # A new configuration is only useful once it has a scoring system, so seed
    # the canonical defaults. They can be edited or reset afterwards.
    await _ensure_default_rules(db, config.id, config.knockout_scoring_basis)

    # If this config is marked active, make sure it is the *only* active one.
    if config.active:
        await db.execute(
            models.PoolConfig.__table__.update()
            .where(models.PoolConfig.id != config.id)
            .values(active=False)
        )

    await db.commit()
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config.id)
    )
    return result.scalar_one()


@router.post("/{config_id}/duplicate", response_model=PoolConfigOut, status_code=201)
async def duplicate_pool_config(
    config_id: uuid.UUID,
    body: PoolConfigDuplicate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Save the rules/settings of an existing config as a new named preset.

    Lets the user keep multiple saved scoring systems instead of overwriting the
    one they are editing. The new config copies every setting and scoring rule of
    the source.
    """
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Pool config not found")

    new_config = models.PoolConfig(
        name=body.name,
        description=body.description if body.description is not None else source.description,
        default_top_n=source.default_top_n,
        candidate_max_goals=source.candidate_max_goals,
        ranking_metric=source.ranking_metric,
        margin_removal_method=source.margin_removal_method,
        group_combine_mode=source.group_combine_mode,
        knockout_combine_mode=source.knockout_combine_mode,
        group_cap=source.group_cap,
        knockout_cap=source.knockout_cap,
        knockout_scoring_basis=source.knockout_scoring_basis,
        pick_lock_minutes_before=source.pick_lock_minutes_before,
        active=body.active,
    )
    db.add(new_config)
    await db.flush()

    for rule in source.scoring_rules:
        db.add(models.ScoringRule(
            pool_config_id=new_config.id,
            code=rule.code,
            label=rule.label,
            description=rule.description,
            points=rule.points,
            enabled=rule.enabled,
            display_specificity_rank=rule.display_specificity_rank,
            phase=rule.phase,
            example=rule.example,
            config=rule.config,
        ))

    if body.active:
        await db.execute(
            models.PoolConfig.__table__.update()
            .where(models.PoolConfig.id != new_config.id)
            .values(active=False)
        )

    await db.commit()
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == new_config.id)
    )
    return result.scalar_one()


@router.get("/{config_id}", response_model=PoolConfigOut)
async def get_pool_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")
    return config


@router.put("/{config_id}", response_model=PoolConfigOut)
async def update_pool_config(
    config_id: uuid.UUID,
    body: PoolConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(config, field, value)

    # If the knockout basis changed, the enabled knockout rules must still be
    # consistent with it.
    if "knockout_scoring_basis" in changes and changes["knockout_scoring_basis"]:
        rules = await _load_rules(db, config_id)
        _assert_consistent(config.knockout_scoring_basis, rules)

    await db.commit()
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config_id)
    )
    return result.scalar_one()


@router.delete("/{config_id}", status_code=204)
async def delete_pool_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Delete a saved pool configuration (and its scoring rules via cascade)."""
    result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    # Zero active configs is allowed — the user always selects a ruleset on the
    # Optimizer page, so we do not auto-promote a replacement.
    await db.delete(config)
    await db.commit()


@router.put("/{config_id}/scoring-rules", response_model=list[ScoringRuleOut])
async def upsert_scoring_rules(
    config_id: uuid.UUID,
    rules: list[ScoringRuleUpsert],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Verify config exists
    result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    # Get existing rules — keyed by (code, phase) since the same code can exist
    # in both group and knockout phases with different point values.
    existing_result = await db.execute(
        select(models.ScoringRule).where(models.ScoringRule.pool_config_id == config_id)
    )
    existing = {(r.code, r.phase): r for r in existing_result.scalars().all()}

    updated = []
    for rule_data in rules:
        key = (rule_data.code, rule_data.phase)
        if key in existing:
            rule = existing[key]
            for field, value in rule_data.model_dump().items():
                setattr(rule, field, value)
        else:
            rule = models.ScoringRule(pool_config_id=config_id, **rule_data.model_dump())
            db.add(rule)
        updated.append(rule)

    # Reject a save that enables knockout rules the pool's basis cannot score.
    full_set = list({id(r): r for r in (*existing.values(), *updated)}.values())
    _assert_consistent(config.knockout_scoring_basis, full_set)

    await db.commit()

    # Reload
    result = await db.execute(
        select(models.ScoringRule)
        .where(models.ScoringRule.pool_config_id == config_id)
        .order_by(models.ScoringRule.display_specificity_rank.asc())
    )
    return result.scalars().all()


@router.post("/{config_id}/activate", response_model=PoolConfigOut)
async def activate_pool_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Make a single pool configuration the active one."""
    result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    # A config can only be activated if its scoring rules are consistent with its
    # knockout basis (so model runs against it are always rule-consistent).
    rules = await _load_rules(db, config_id)
    _assert_consistent(config.knockout_scoring_basis, rules)

    await db.execute(models.PoolConfig.__table__.update().values(active=False))
    config.active = True
    await db.commit()

    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config_id)
    )
    return result.scalar_one()


@router.get("/{config_id}/scoring-rules", response_model=list[ScoringRuleOut])
async def get_scoring_rules(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """List the scoring rules for a config, seeding defaults if it has none."""
    result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    rules = await _load_rules(db, config_id)
    if not rules:
        await _ensure_default_rules(db, config_id, config.knockout_scoring_basis)
        await db.commit()
        rules = await _load_rules(db, config_id)
    else:
        # Presets created before knockout support only have group rules. Auto-seed
        # the missing knockout rules without touching the user's custom group values.
        existing_phases = {r.phase for r in rules}
        if "knockout" not in existing_phases:
            ko_defaults = _reconcile_rules_for_basis(
                [r for r in get_default_rules() if r["phase"] == "knockout"],
                config.knockout_scoring_basis,
            )
            for rule_data in ko_defaults:
                db.add(models.ScoringRule(pool_config_id=config_id, **rule_data))
            await db.commit()
            rules = await _load_rules(db, config_id)
    return rules


@router.patch("/{config_id}/scoring-rules/{rule_id}", response_model=ScoringRuleOut)
async def patch_scoring_rule(
    config_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: ScoringRulePatch,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Update the points and/or enabled flag of a single scoring rule."""
    result = await db.execute(
        select(models.ScoringRule).where(
            models.ScoringRule.id == rule_id,
            models.ScoringRule.pool_config_id == config_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Scoring rule not found")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)

    # Toggling a knockout bonus on must remain consistent with the pool's basis.
    config_result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = config_result.scalar_one_or_none()
    if config is not None:
        rules = await _load_rules(db, config_id)
        _assert_consistent(config.knockout_scoring_basis, rules)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.post("/{config_id}/scoring-rules/reset", response_model=list[ScoringRuleOut])
async def reset_scoring_rules(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Delete all scoring rules for a config and recreate the defaults."""
    result = await db.execute(
        select(models.PoolConfig).where(models.PoolConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    existing = await _load_rules(db, config_id)
    for rule in existing:
        await db.delete(rule)
    await db.flush()

    await _ensure_default_rules(db, config_id, config.knockout_scoring_basis)
    await db.commit()
    return await _load_rules(db, config_id)

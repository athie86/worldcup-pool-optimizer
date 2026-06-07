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
from ..core.defaults import DEFAULT_SCORING_RULES
from .deps import get_current_user

router = APIRouter()


async def _ensure_default_rules(db: AsyncSession, config_id: uuid.UUID) -> None:
    """Seed the canonical default scoring rules for a config that has none."""
    for rule_data in DEFAULT_SCORING_RULES:
        db.add(models.ScoringRule(pool_config_id=config_id, **rule_data))


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
    await _ensure_default_rules(db, config.id)

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
        scoring_mode=source.scoring_mode,
        binary_result_points=source.binary_result_points,
        binary_total_goals_points=source.binary_total_goals_points,
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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

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

    was_active = config.active
    await db.delete(config)
    await db.flush()

    # If we removed the active config, promote the oldest remaining one so the
    # app always has an active configuration to run against.
    if was_active:
        remaining = await db.execute(
            select(models.PoolConfig).order_by(models.PoolConfig.created_at.asc()).limit(1)
        )
        next_config = remaining.scalar_one_or_none()
        if next_config:
            next_config.active = True

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

    # Get existing rules
    existing_result = await db.execute(
        select(models.ScoringRule).where(models.ScoringRule.pool_config_id == config_id)
    )
    existing = {r.code: r for r in existing_result.scalars().all()}

    updated = []
    for rule_data in rules:
        if rule_data.code in existing:
            rule = existing[rule_data.code]
            for field, value in rule_data.model_dump().items():
                setattr(rule, field, value)
        else:
            rule = models.ScoringRule(pool_config_id=config_id, **rule_data.model_dump())
            db.add(rule)
        updated.append(rule)

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
        await _ensure_default_rules(db, config_id)
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

    await _ensure_default_rules(db, config_id)
    await db.commit()
    return await _load_rules(db, config_id)

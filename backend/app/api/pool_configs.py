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
    ScoringRuleUpsert,
    ScoringRuleOut,
)
from .deps import get_current_user

router = APIRouter()


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
    await db.commit()
    await db.refresh(config)
    result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == config.id)
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

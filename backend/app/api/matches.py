from __future__ import annotations
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.matches import MatchOut, MatchCreate, MatchUpdate
from .deps import get_current_user

router = APIRouter()


@router.get("/matches", response_model=list[MatchOut])
async def list_matches(
    stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    complete_for_optimization: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = (
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
        )
        .order_by(models.Match.match_number.asc().nullslast(), models.Match.kickoff_at.asc().nullslast())
    )
    if stage is not None:
        q = q.where(models.Match.stage == stage)
    if status is not None:
        q = q.where(models.Match.status == status)
    if complete_for_optimization is not None:
        q = q.where(models.Match.is_complete_for_optimization == complete_for_optimization)

    result = await db.execute(q)
    return result.scalars().all()


@router.post("/matches", response_model=MatchOut, status_code=201)
async def create_match(
    body: MatchCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    match = models.Match(**body.model_dump())
    db.add(match)
    await db.commit()
    await db.refresh(match)
    # reload with relations
    result = await db.execute(
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
        )
        .where(models.Match.id == match.id)
    )
    return result.scalar_one()


@router.put("/matches/{match_id}", response_model=MatchOut)
async def update_match(
    match_id: uuid.UUID,
    body: MatchUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
        )
        .where(models.Match.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(match, field, value)

    await db.commit()
    await db.refresh(match)
    result = await db.execute(
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
        )
        .where(models.Match.id == match_id)
    )
    return result.scalar_one()


@router.delete("/matches/{match_id}", status_code=204)
async def delete_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(models.Match).where(models.Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    await db.delete(match)
    await db.commit()


@router.post("/matches/import-provider-schedule")
async def import_provider_schedule(_: str = Depends(get_current_user)):
    return {"message": "Provider schedule import not yet implemented. Use POST /matches to create matches manually."}

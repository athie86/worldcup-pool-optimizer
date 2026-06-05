"""Service for syncing matches with odds provider schedules."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db import models
from ..core.logging import logger


async def match_event_to_db(
    db: AsyncSession,
    provider_event_id: str,
    home_team: str,
    away_team: str,
    commence_time: Optional[datetime],
    sport_key: str,
) -> Optional[models.Match]:
    """Find existing match by provider_event_id."""
    result = await db.execute(
        select(models.Match).where(models.Match.provider_event_id == provider_event_id)
    )
    return result.scalar_one_or_none()

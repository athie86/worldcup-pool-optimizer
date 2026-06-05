from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.odds import (
    OddsSnapshotOut,
    OddsEventOut,
    ManualOddsOverrideOut,
    ManualOddsOverrideUpsert,
    OddsRefreshRequest,
    OddsRefreshResponse,
)
from ..core.config import settings
from ..core.logging import logger
from .deps import get_current_user

router = APIRouter()


async def _do_odds_refresh(
    db: AsyncSession,
    sport_key: str,
    markets: list[str],
    regions: list[str],
    bookmakers: list[str],
) -> models.OddsSnapshot:
    """Perform actual odds fetch from provider and store in DB."""
    if settings.ODDS_PROVIDER == "the_odds_api":
        from ..services.odds_provider_the_odds_api import TheOddsApiProvider
        provider = TheOddsApiProvider(settings.ODDS_API_KEY)
    else:
        raise HTTPException(status_code=500, detail=f"Unknown odds provider: {settings.ODDS_PROVIDER}")

    snapshot = models.OddsSnapshot(
        provider=settings.ODDS_PROVIDER,
        requested_markets=markets,
        requested_regions=regions,
        requested_bookmakers=bookmakers,
        fetched_at=datetime.utcnow(),
        status="pending",
    )
    db.add(snapshot)
    await db.flush()

    try:
        events, request_url, raw = await provider.fetch_odds(
            sport_key=sport_key,
            markets=markets,
            regions=regions or None,
            bookmakers=bookmakers or None,
        )
        snapshot.status = "success"
        snapshot.request_url = request_url
        snapshot.raw_response = raw

        # Persist events
        for evt in events:
            # Try to find matching match by provider_event_id
            match_result = await db.execute(
                select(models.Match).where(models.Match.provider_event_id == evt.id)
            )
            match = match_result.scalar_one_or_none()

            odds_event = models.OddsEvent(
                odds_snapshot_id=snapshot.id,
                match_id=match.id if match else None,
                provider_event_id=evt.id,
                sport_key=evt.sport_key,
                home_team=evt.home_team,
                away_team=evt.away_team,
                commence_time=evt.commence_time,
            )
            db.add(odds_event)
            await db.flush()

            for bk in evt.bookmakers:
                for mkt in bk.markets:
                    bm = models.BookmakerMarket(
                        odds_event_id=odds_event.id,
                        bookmaker_key=bk.key,
                        bookmaker_title=bk.title,
                        market_key=mkt.key,
                        last_update=mkt.last_update,
                        line=mkt.line,
                    )
                    db.add(bm)
                    await db.flush()

                    for outcome in mkt.outcomes:
                        raw_price = outcome.price if hasattr(outcome, 'price') else 0.0
                        implied = 1.0 / raw_price if raw_price > 0 else None
                        mo = models.MarketOutcome(
                            bookmaker_market_id=bm.id,
                            outcome_name=outcome.name,
                            outcome_type=outcome.name,  # name is already typed
                            price_decimal=raw_price,
                            implied_probability=implied,
                        )
                        db.add(mo)

    except Exception as exc:
        snapshot.status = "error"
        snapshot.error_message = str(exc)
        logger.error("odds_refresh: failed", error=str(exc))

    await db.commit()
    return snapshot


@router.post("/odds/refresh", response_model=OddsRefreshResponse)
async def refresh_odds(
    body: OddsRefreshRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    sport_key = body.sport_key or settings.ODDS_SPORT_KEY
    markets = body.markets or settings.ODDS_MARKETS
    regions = body.regions or settings.ODDS_REGIONS
    bookmakers = body.bookmakers or settings.ODDS_BOOKMAKERS

    snapshot = await _do_odds_refresh(db, sport_key, markets, regions, bookmakers)

    # Count events
    result = await db.execute(
        select(models.OddsEvent).where(models.OddsEvent.odds_snapshot_id == snapshot.id)
    )
    events = result.scalars().all()

    return OddsRefreshResponse(
        snapshot_id=snapshot.id,
        status=snapshot.status,
        events_count=len(events),
        message=snapshot.error_message,
    )


@router.get("/odds/snapshots", response_model=list[OddsSnapshotOut])
async def list_snapshots(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.OddsSnapshot)
        .order_by(models.OddsSnapshot.fetched_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/matches/{match_id}/odds", response_model=list[OddsEventOut])
async def get_match_odds(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.OddsEvent)
        .options(
            selectinload(models.OddsEvent.bookmaker_markets).selectinload(
                models.BookmakerMarket.market_outcomes
            )
        )
        .where(models.OddsEvent.match_id == match_id)
        .order_by(models.OddsEvent.created_at.desc())
    )
    return result.scalars().all()


@router.put("/matches/{match_id}/odds-overrides", response_model=list[ManualOddsOverrideOut])
async def upsert_odds_overrides(
    match_id: uuid.UUID,
    overrides: list[ManualOddsOverrideUpsert],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Verify match exists
    result = await db.execute(select(models.Match).where(models.Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Load existing overrides
    existing_result = await db.execute(
        select(models.ManualOddsOverride).where(
            models.ManualOddsOverride.match_id == match_id
        )
    )
    existing_map = {
        (o.market_key, o.line, o.outcome_type): o
        for o in existing_result.scalars().all()
    }

    for ov_data in overrides:
        key = (ov_data.market_key, ov_data.line, ov_data.outcome_type)
        if key in existing_map:
            ov = existing_map[key]
            ov.price_decimal = ov_data.price_decimal
            ov.enabled = ov_data.enabled
            ov.reason = ov_data.reason
        else:
            ov = models.ManualOddsOverride(
                match_id=match_id,
                **ov_data.model_dump(),
            )
            db.add(ov)

    await db.commit()

    result = await db.execute(
        select(models.ManualOddsOverride).where(
            models.ManualOddsOverride.match_id == match_id
        )
    )
    return result.scalars().all()

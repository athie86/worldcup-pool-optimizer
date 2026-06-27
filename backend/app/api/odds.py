from __future__ import annotations
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
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
    MatchOddsOut,
    MatchBookmakerMarketOut,
    MatchMarketOutcomeOut,
    ConsensusProbabilitiesOut,
)
from ..core.config import settings
from ..core.logging import logger
from ..services.odds_normalization import (
    RawOutcome,
    BookmakerMarket as ConsensusBookmakerMarket,
    normalize_market,
    compute_consensus,
)
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
        fetched_at=datetime.now(timezone.utc),
        status="pending",
    )
    db.add(snapshot)
    await db.flush()

    # Fail fast with a clear, human-readable message when the provider is not
    # configured, instead of surfacing a cryptic provider 401.
    if settings.ODDS_PROVIDER == "the_odds_api" and not settings.ODDS_API_KEY:
        snapshot.status = "error"
        snapshot.error_message = (
            "ODDS_API_KEY is not configured. Add your The Odds API key to the "
            "environment (ODDS_API_KEY) and redeploy/restart the backend to fetch live odds."
        )
        logger.error("odds_refresh: missing ODDS_API_KEY")
        await db.commit()
        return snapshot

    try:
        events, request_url, raw = await provider.fetch_odds(
            sport_key=sport_key,
            markets=markets,
            regions=regions or None,
            bookmakers=bookmakers or None,
        )
        snapshot.status = "success"
        snapshot.request_url = request_url
        snapshot.raw_response = {
            "event_count": len(events),
            "request_url": request_url,
        }

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
    body: OddsRefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Manual refresh is intentionally the only way odds are fetched (there is no
    # background scheduler). The request body is optional; when omitted we fall
    # back to the configured defaults.
    body = body or OddsRefreshRequest()
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


def _to_float(value) -> Optional[float]:
    return float(value) if value is not None else None


@router.get("/odds/matches/{match_id}", response_model=MatchOddsOut)
async def get_match_market_odds(
    match_id: uuid.UUID,
    snapshot_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Aggregated odds for a match, scoped to a single snapshot.

    When ``snapshot_id`` is omitted we use the most recent snapshot that has
    odds for this match. Odds are never fetched here — only the latest data
    already pulled via a manual refresh is returned.
    """
    query = (
        select(models.OddsEvent)
        .join(models.OddsSnapshot, models.OddsEvent.odds_snapshot_id == models.OddsSnapshot.id)
        .options(
            selectinload(models.OddsEvent.bookmaker_markets).selectinload(
                models.BookmakerMarket.market_outcomes
            ),
            selectinload(models.OddsEvent.odds_snapshot),
        )
        .where(models.OddsEvent.match_id == match_id)
        .order_by(models.OddsSnapshot.fetched_at.desc())
    )
    if snapshot_id is not None:
        query = query.where(models.OddsEvent.odds_snapshot_id == snapshot_id)

    event = (await db.execute(query)).scalars().first()

    bookmaker_markets_out: list[MatchBookmakerMarketOut] = []
    consensus_input: list[ConsensusBookmakerMarket] = []

    if event is not None:
        for bm in event.bookmaker_markets:
            line = _to_float(bm.line)
            raw_outcomes = [
                RawOutcome(
                    outcome_type=o.outcome_type,
                    price_decimal=float(o.price_decimal),
                    line=line,
                )
                for o in bm.market_outcomes
                if o.price_decimal is not None
            ]
            normalized = normalize_market(raw_outcomes)
            bookmaker_markets_out.append(
                MatchBookmakerMarketOut(
                    bookmaker_key=bm.bookmaker_key,
                    market_key=bm.market_key,
                    line=line,
                    outcomes=[
                        MatchMarketOutcomeOut(
                            outcome_type=o.outcome_type,
                            price_decimal=o.price_decimal,
                            normalized_probability=normalized.get(o.outcome_type),
                        )
                        for o in raw_outcomes
                    ],
                )
            )
            consensus_input.append(
                ConsensusBookmakerMarket(
                    bookmaker_key=bm.bookmaker_key,
                    market_key=bm.market_key,
                    line=line,
                    outcomes=raw_outcomes,
                )
            )

    overrides = (
        (
            await db.execute(
                select(models.ManualOddsOverride)
                .where(models.ManualOddsOverride.match_id == match_id)
                .order_by(models.ManualOddsOverride.created_at)
            )
        )
        .scalars()
        .all()
    )

    override_outcomes = [
        RawOutcome(
            outcome_type=ov.outcome_type,
            price_decimal=float(ov.price_decimal),
            line=_to_float(ov.line),
        )
        for ov in overrides
        if ov.enabled
    ]

    consensus = compute_consensus(consensus_input, override_outcomes or None)

    return MatchOddsOut(
        match_id=match_id,
        snapshot_id=event.odds_snapshot_id if event else None,
        fetched_at=event.odds_snapshot.fetched_at if event and event.odds_snapshot else None,
        bookmaker_markets=bookmaker_markets_out,
        consensus_probabilities=ConsensusProbabilitiesOut(**asdict(consensus)),
        overrides=overrides,
    )


@router.get("/odds/matches/{match_id}/overrides", response_model=list[ManualOddsOverrideOut])
async def list_match_overrides(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.ManualOddsOverride)
        .where(models.ManualOddsOverride.match_id == match_id)
        .order_by(models.ManualOddsOverride.created_at)
    )
    return result.scalars().all()


@router.post("/odds/matches/{match_id}/overrides", response_model=ManualOddsOverrideOut)
async def create_match_override(
    match_id: uuid.UUID,
    body: ManualOddsOverrideUpsert,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    match = (
        await db.execute(select(models.Match).where(models.Match.id == match_id))
    ).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    existing = (
        await db.execute(
            select(models.ManualOddsOverride).where(
                models.ManualOddsOverride.match_id == match_id,
                models.ManualOddsOverride.market_key == body.market_key,
                models.ManualOddsOverride.line == body.line,
                models.ManualOddsOverride.outcome_type == body.outcome_type,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.price_decimal = body.price_decimal
        existing.enabled = body.enabled
        existing.reason = body.reason
        override = existing
    else:
        override = models.ManualOddsOverride(match_id=match_id, **body.model_dump())
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return override


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

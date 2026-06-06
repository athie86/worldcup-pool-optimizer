from __future__ import annotations
import csv
import io
import json
import uuid
from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.matches import (
    MatchOut,
    MatchCreate,
    MatchUpdate,
    MatchListItem,
    PaginatedMatches,
    ImportSummary,
    DashboardStats,
)
from ..core.config import settings
from ..core.logging import logger
from .deps import get_current_user

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _to_list_item(match: models.Match) -> MatchListItem:
    """Flatten an ORM match (with relations loaded) into the list shape."""
    return MatchListItem(
        id=match.id,
        provider_event_id=match.provider_event_id,
        match_number=match.match_number,
        stage=match.stage,
        group_label=match.group_label,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_team=match.home_team.name if match.home_team else None,
        away_team=match.away_team.name if match.away_team else None,
        home_placeholder=match.home_placeholder,
        away_placeholder=match.away_placeholder,
        venue=match.venue,
        city=match.city,
        country=match.country,
        kickoff_at=match.kickoff_at,
        status=match.status,
        scoring_basis=match.scoring_basis,
        is_manual=match.is_manual,
        is_complete_for_optimization=match.is_complete_for_optimization,
        has_overrides=any(o.enabled for o in match.manual_overrides),
        has_odds=len(match.odds_events) > 0,
        fit_status=None,
    )


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        # Tolerate a plain date.
        try:
            return datetime.fromisoformat(s + "T00:00:00+00:00")
        except ValueError:
            return None


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t")


class _TeamResolver:
    """Get-or-create teams by name, caching within a single import request."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict[str, models.Team] = {}
        self.created = 0

    async def resolve(self, name: Optional[str]) -> Optional[models.Team]:
        if not name:
            return None
        key = name.strip()
        if not key:
            return None
        if key in self._cache:
            return self._cache[key]
        result = await self.db.execute(
            select(models.Team).where(func.lower(models.Team.name) == key.lower())
        )
        team = result.scalar_one_or_none()
        if not team:
            team = models.Team(name=key, short_name=key[:3].upper())
            self.db.add(team)
            await self.db.flush()
            self.created += 1
        self._cache[key] = team
        return team


def _get(row: dict, *keys: str) -> Any:
    """Case-insensitive lookup across several possible column names."""
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key in lowered and lowered[key] not in (None, ""):
            return lowered[key]
    return None


async def _upsert_match_from_row(
    db: AsyncSession, resolver: _TeamResolver, row: dict
) -> tuple[bool, bool]:
    """Create or update a match from a dict row. Returns (created, updated)."""
    stage = _get(row, "stage") or "group"
    home_name = _get(row, "home_team", "home")
    away_name = _get(row, "away_team", "away")
    home_placeholder = _get(row, "home_placeholder")
    away_placeholder = _get(row, "away_placeholder")

    if not home_name and not home_placeholder:
        raise ValueError("missing home team")
    if not away_name and not away_placeholder:
        raise ValueError("missing away team")

    home_team = await resolver.resolve(home_name)
    away_team = await resolver.resolve(away_name)

    match_number_raw = _get(row, "match_number", "match", "#")
    match_number = int(match_number_raw) if match_number_raw is not None else None
    provider_event_id = _get(row, "provider_event_id")

    # Both teams resolved -> ready for optimization unless explicitly overridden.
    default_complete = bool(home_team and away_team)

    fields = dict(
        stage=str(stage),
        group_label=_get(row, "group_label", "group"),
        home_team_id=home_team.id if home_team else None,
        away_team_id=away_team.id if away_team else None,
        home_placeholder=home_placeholder,
        away_placeholder=away_placeholder,
        venue=_get(row, "venue"),
        city=_get(row, "city"),
        country=_get(row, "country"),
        kickoff_at=_parse_dt(_get(row, "kickoff_at", "kickoff", "date")),
        scoring_basis=_get(row, "scoring_basis") or "ninety_minutes",
        match_number=match_number,
        provider_event_id=provider_event_id,
        is_complete_for_optimization=_parse_bool(
            _get(row, "is_complete_for_optimization", "complete"), default_complete
        ),
    )

    # Find an existing match to update (by match_number, then provider_event_id).
    existing = None
    if match_number is not None:
        res = await db.execute(
            select(models.Match).where(models.Match.match_number == match_number)
        )
        existing = res.scalar_one_or_none()
    if existing is None and provider_event_id:
        res = await db.execute(
            select(models.Match).where(
                models.Match.provider_event_id == provider_event_id
            )
        )
        existing = res.scalar_one_or_none()

    if existing:
        for field, value in fields.items():
            if value is not None:
                setattr(existing, field, value)
        return (False, True)

    db.add(models.Match(is_manual=True, status="scheduled", **fields))
    return (True, False)


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("/matches", response_model=PaginatedMatches)
async def list_matches(
    stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    complete_for_optimization: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    base = select(models.Match)
    if stage is not None:
        base = base.where(models.Match.stage == stage)
    if status is not None:
        base = base.where(models.Match.status == status)
    if complete_for_optimization is not None:
        base = base.where(
            models.Match.is_complete_for_optimization == complete_for_optimization
        )

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = total_result.scalar_one()

    q = (
        base.options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
            selectinload(models.Match.manual_overrides),
            selectinload(models.Match.odds_events),
        )
        .order_by(
            models.Match.match_number.asc().nullslast(),
            models.Match.kickoff_at.asc().nullslast(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = [_to_list_item(m) for m in result.scalars().all()]
    return PaginatedMatches(items=items, total=total, page=page, page_size=page_size)


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
    result = await db.execute(
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
        )
        .where(models.Match.id == match.id)
    )
    return result.scalar_one()


@router.post("/matches/import", response_model=ImportSummary)
async def import_schedule(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Import a match schedule from an uploaded CSV or JSON file.

    CSV: a header row with any of these columns (case-insensitive):
      match_number, stage, group_label, home_team, away_team, kickoff_at,
      venue, city, country, scoring_basis, provider_event_id,
      is_complete_for_optimization

    JSON: an array of objects with the same keys, or {"matches": [...]}.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text.")

    filename = (file.filename or "").lower()
    rows: list[dict]
    if filename.endswith(".json") or text.lstrip().startswith(("[", "{")):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
        if isinstance(parsed, dict):
            parsed = parsed.get("matches", [])
        if not isinstance(parsed, list):
            raise HTTPException(
                status_code=400,
                detail="JSON must be an array of matches or {\"matches\": [...]}.",
            )
        rows = parsed
    else:
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(r) for r in reader]

    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in file.")

    resolver = _TeamResolver(db)
    created = updated = skipped = 0
    errors: list[str] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            skipped += 1
            errors.append(f"Row {i}: not an object")
            continue
        try:
            was_created, was_updated = await _upsert_match_from_row(db, resolver, row)
            created += int(was_created)
            updated += int(was_updated)
        except Exception as exc:  # noqa: BLE001 - report row-level failures
            skipped += 1
            errors.append(f"Row {i}: {exc}")

    await db.commit()
    return ImportSummary(
        message=f"Imported {created} new and updated {updated} match(es).",
        created=created,
        updated=updated,
        teams_created=resolver.created,
        skipped=skipped,
        errors=errors[:20],
    )


@router.post("/matches/import-provider-schedule", response_model=ImportSummary)
async def import_provider_schedule(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Import the match schedule (fixtures) directly from the odds provider."""
    if settings.ODDS_PROVIDER != "the_odds_api":
        return ImportSummary(
            message=f"Provider schedule import is not supported for provider "
            f"'{settings.ODDS_PROVIDER}'."
        )
    if not settings.ODDS_API_KEY:
        return ImportSummary(
            message="ODDS_API_KEY is not configured. Add it to the environment to "
            "import fixtures from The Odds API, or upload a CSV/JSON file instead."
        )

    from ..services.odds_provider_the_odds_api import TheOddsApiProvider

    provider = TheOddsApiProvider(settings.ODDS_API_KEY)
    try:
        events = await provider.fetch_events(settings.ODDS_SPORT_KEY)
    except Exception as exc:  # noqa: BLE001 - surface provider failures to the UI
        logger.error("import_provider_schedule: failed", error=str(exc))
        return ImportSummary(message=f"Failed to fetch schedule from provider: {exc}")

    resolver = _TeamResolver(db)
    created = updated = 0
    errors: list[str] = []
    for evt in events:
        try:
            home = await resolver.resolve(evt.home_team)
            away = await resolver.resolve(evt.away_team)
            res = await db.execute(
                select(models.Match).where(
                    models.Match.provider_event_id == evt.id
                )
            )
            existing = res.scalar_one_or_none()
            if existing:
                existing.home_team_id = home.id if home else existing.home_team_id
                existing.away_team_id = away.id if away else existing.away_team_id
                existing.kickoff_at = evt.commence_time or existing.kickoff_at
                updated += 1
            else:
                db.add(
                    models.Match(
                        provider_event_id=evt.id,
                        stage="group",
                        home_team_id=home.id if home else None,
                        away_team_id=away.id if away else None,
                        kickoff_at=evt.commence_time,
                        status="scheduled",
                        scoring_basis="ninety_minutes",
                        is_manual=False,
                        is_complete_for_optimization=bool(home and away),
                    )
                )
                created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{evt.home_team} vs {evt.away_team}: {exc}")

    await db.commit()
    return ImportSummary(
        message=f"Imported {created} new and updated {updated} match(es) from The Odds API.",
        created=created,
        updated=updated,
        teams_created=resolver.created,
        errors=errors[:20],
    )


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Latest successful odds refresh.
    snap_result = await db.execute(
        select(models.OddsSnapshot.fetched_at)
        .where(models.OddsSnapshot.status == "success")
        .order_by(models.OddsSnapshot.fetched_at.desc())
        .limit(1)
    )
    latest_refresh = snap_result.scalar_one_or_none()

    ready_result = await db.execute(
        select(func.count()).where(
            models.Match.is_complete_for_optimization == True  # noqa: E712
        )
    )
    incomplete_result = await db.execute(
        select(func.count()).where(
            models.Match.is_complete_for_optimization == False  # noqa: E712
        )
    )
    with_overrides_result = await db.execute(
        select(func.count(func.distinct(models.ManualOddsOverride.match_id))).where(
            models.ManualOddsOverride.enabled == True  # noqa: E712
        )
    )
    ready_count = int(ready_result.scalar_one())
    incomplete_count = int(incomplete_result.scalar_one())
    with_overrides_count = int(with_overrides_result.scalar_one())

    # Latest model run + a small summary derived from its fits.
    run_result = await db.execute(
        select(models.ModelRun)
        .options(selectinload(models.ModelRun.match_model_fits))
        .order_by(models.ModelRun.started_at.desc().nullslast())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()

    latest_model_run = None
    avg_fit_quality = "pending"
    if run:
        fits = run.match_model_fits
        optimized = sum(1 for f in fits if f.lambda_home is not None)
        warnings = sum(1 for f in fits if (f.fit_status or "") not in ("good", "acceptable"))
        latest_model_run = {
            "id": str(run.id),
            "status": run.status,
            "run_type": run.run_type,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "summary": {
                "matches_total": len(fits),
                "optimized": optimized,
                "incomplete": incomplete_count,
                "warnings": warnings,
            },
        }
        statuses = [f.fit_status for f in fits if f.fit_status]
        if statuses:
            if all(s == "good" for s in statuses):
                avg_fit_quality = "good"
            elif any(s == "weak" for s in statuses):
                avg_fit_quality = "weak"
            else:
                avg_fit_quality = "acceptable"

    return DashboardStats(
        latest_odds_refresh=latest_refresh,
        matches_ready=ready_count,
        matches_incomplete=incomplete_count,
        matches_with_overrides=with_overrides_count,
        latest_model_run=latest_model_run,
        avg_fit_quality=avg_fit_quality,
    )


@router.get("/matches/{match_id}", response_model=MatchOut)
async def get_match(
    match_id: uuid.UUID,
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
    return match


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

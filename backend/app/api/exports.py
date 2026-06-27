from __future__ import annotations
import uuid
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.exports import ExportOut, ExportCreateRequest, ExportDispatchRequest
from ..services.export_service import build_csv, build_excel, save_export
from ..core.config import settings
from .deps import get_current_user

router = APIRouter()


async def _load_run_with_fits(db: AsyncSession, run_id: uuid.UUID) -> models.ModelRun:
    result = await db.execute(
        select(models.ModelRun)
        .options(
            selectinload(models.ModelRun.pool_config).selectinload(
                models.PoolConfig.scoring_rules
            ),
            selectinload(models.ModelRun.match_model_fits)
            .selectinload(models.MatchModelFit.score_recommendations),
            selectinload(models.ModelRun.match_model_fits)
            .selectinload(models.MatchModelFit.match)
            .selectinload(models.Match.home_team),
            selectinload(models.ModelRun.match_model_fits)
            .selectinload(models.MatchModelFit.match)
            .selectinload(models.Match.away_team),
            selectinload(models.ModelRun.match_model_fits)
            .selectinload(models.MatchModelFit.match)
            .selectinload(models.Match.manual_overrides),
        )
        .where(models.ModelRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Model run not found")
    return run


@router.get("", response_model=list[ExportOut])
async def list_exports(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.Export)
        .order_by(models.Export.created_at.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.post("", response_model=ExportOut, status_code=201)
async def create_export_dispatch(
    body: ExportDispatchRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Dispatch endpoint: frontend posts {format, model_run_id} here."""
    run = await _load_run_with_fits(db, body.model_run_id)
    fits = run.match_model_fits
    top_n = body.top_n or 3
    fmt = body.format.lower().lstrip(".")

    if fmt in ("xlsx", "excel"):
        content = build_excel(run, fits, top_n=top_n)
        ext = "xlsx"
        export_type = "excel"
    else:
        content = build_csv(run, fits, top_n=top_n)
        ext = "csv"
        export_type = "csv"

    filename = f"export_{run.id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{ext}"
    path = save_export(content, settings.EXPORT_DIR, filename)

    export = models.Export(model_run_id=run.id, export_type=export_type, file_path=path)
    db.add(export)
    await db.commit()
    await db.refresh(export)
    return export


@router.post("/csv", response_model=ExportOut, status_code=201)
async def export_csv(
    body: ExportCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    run = await _load_run_with_fits(db, body.model_run_id)
    fits = run.match_model_fits
    top_n = body.top_n or 3
    content = build_csv(run, fits, top_n=top_n)

    filename = f"export_{run.id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    path = save_export(content, settings.EXPORT_DIR, filename)

    export = models.Export(model_run_id=run.id, export_type="csv", file_path=path)
    db.add(export)
    await db.commit()
    await db.refresh(export)
    return export


@router.post("/excel", response_model=ExportOut, status_code=201)
async def export_excel(
    body: ExportCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    run = await _load_run_with_fits(db, body.model_run_id)
    fits = run.match_model_fits
    top_n = body.top_n or 3
    content = build_excel(run, fits, top_n=top_n)

    filename = f"export_{run.id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    path = save_export(content, settings.EXPORT_DIR, filename)

    export = models.Export(model_run_id=run.id, export_type="excel", file_path=path)
    db.add(export)
    await db.commit()
    await db.refresh(export)
    return export


@router.get("/{export_id}/download")
async def download_export(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.Export).where(models.Export.id == export_id)
    )
    export = result.scalar_one_or_none()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if not export.file_path or not os.path.exists(export.file_path):
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    media_type = "text/csv" if export.export_type == "csv" else \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = os.path.basename(export.file_path)

    return FileResponse(
        path=export.file_path,
        media_type=media_type,
        filename=filename,
    )

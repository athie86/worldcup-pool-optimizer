"""APScheduler background jobs."""
from __future__ import annotations
from datetime import datetime
from ..core.logging import logger


async def refresh_odds_job():
    """Scheduled job: refresh odds from provider."""
    logger.info("refresh_odds_job: starting")
    try:
        from ..db.session import AsyncSessionLocal
        from ..core.config import settings
        # Lazy import to avoid circular deps
        async with AsyncSessionLocal() as db:
            from .jobs_impl import run_odds_refresh
            await run_odds_refresh(db, settings)
    except Exception as exc:
        logger.error("refresh_odds_job: failed", error=str(exc))


async def run_optimizer_job(pool_config_id: str, odds_snapshot_id: str):
    """Scheduled job: run optimizer after odds refresh."""
    logger.info("run_optimizer_job: starting", pool_config_id=pool_config_id)
    try:
        from ..db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            from .jobs_impl import run_optimizer
            import uuid
            await run_optimizer(db, uuid.UUID(pool_config_id), uuid.UUID(odds_snapshot_id))
    except Exception as exc:
        logger.error("run_optimizer_job: failed", error=str(exc))

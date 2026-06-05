from fastapi import APIRouter
from sqlalchemy import text
from ..db.session import AsyncSessionLocal
from ..core.config import settings
from ..schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.VERSION,
        database=db_status,
    )

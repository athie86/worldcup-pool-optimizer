from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..core.config import settings
from .deps import get_current_user

router = APIRouter()


class AppSettingsOut(BaseModel):
    odds_sport_key: str
    odds_regions: list[str]
    odds_bookmakers: list[str]
    refresh_hour_utc: int
    refresh_timezone: str
    auto_run_optimizer: bool
    odds_api_key_configured: bool


@router.get("", response_model=AppSettingsOut)
async def get_settings(_: str = Depends(get_current_user)):
    return AppSettingsOut(
        odds_sport_key=settings.ODDS_SPORT_KEY,
        odds_regions=settings.ODDS_REGIONS,
        odds_bookmakers=settings.ODDS_BOOKMAKERS,
        refresh_hour_utc=settings.REFRESH_HOUR_LOCAL,
        refresh_timezone=settings.TIMEZONE,
        auto_run_optimizer=settings.AUTO_RUN_OPTIMIZER_AFTER_REFRESH,
        odds_api_key_configured=bool(settings.ODDS_API_KEY),
    )

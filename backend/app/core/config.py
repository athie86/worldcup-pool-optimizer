from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import secrets
import sys


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://worldcup:worldcup@localhost:5432/worldcup"
    ODDS_API_KEY: str = ""
    ADMIN_PASSWORD: str = ""
    SESSION_SECRET: str = ""

    @field_validator("SESSION_SECRET")
    @classmethod
    def ensure_session_secret(cls, v: str) -> str:
        if not v:
            # In production, a missing SESSION_SECRET means every restart
            # invalidates all sessions. Log a clear warning and generate a
            # random secret so the app still starts.
            import os
            if os.environ.get("ENVIRONMENT", "development") == "production":
                print(
                    "WARNING: SESSION_SECRET is not set in production. "
                    "Sessions will be invalidated on every restart. "
                    "Set SESSION_SECRET in your environment.",
                    file=sys.stderr,
                )
            return secrets.token_hex(32)
        return v

    APP_BASE_URL: str = "http://localhost:3000"
    ENVIRONMENT: str = "development"
    TIMEZONE: str = "America/Mexico_City"

    # Odds provider settings
    ODDS_PROVIDER: str = "the_odds_api"
    ODDS_SPORT_KEY: str = "soccer_fifa_world_cup"
    ODDS_REGIONS: list[str] = ["eu", "uk", "us"]
    ODDS_BOOKMAKERS: list[str] = []
    ODDS_MARKETS: list[str] = ["h2h", "totals"]
    ODDS_FORMAT: str = "decimal"
    REFRESH_HOUR_LOCAL: int = 7

    # Scheduler
    AUTO_RUN_OPTIMIZER_AFTER_REFRESH: bool = False

    # Export
    EXPORT_DIR: str = "/app/exports"

    # App version
    VERSION: str = "0.1.0"


settings = Settings()

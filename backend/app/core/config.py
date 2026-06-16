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

    # ── Prediction model V2 feature flags (spec WCPO-PRED-MODEL-V2 §14.2) ──────
    # Default to v1 so existing behaviour is unchanged until v2 is validated.
    # v2 can be selected globally here or per-run via ModelRunCreate.parameters
    # ({"model_version": "v2"}). The model registry always falls back to v1 (and
    # then a neutral matrix) if v2 fails, so enabling v2 can never abort a run.
    PREDICTION_MODEL_VERSION: str = "v1"          # "v1" | "v2"
    V1_FALLBACK_ENABLED: bool = True
    ENABLE_RICH_ODDS_REFRESH: bool = False
    ENABLE_MARKET_CONSTRAINT_STORAGE: bool = True
    ENABLE_BACKTESTING: bool = False
    ENABLE_FUNDAMENTAL_PRIOR: bool = True
    ENABLE_ASIAN_LINE_SUPPORT: bool = True

    # V2 score-grid configuration
    ACTUAL_SCORE_MAX: int = 12                    # full actual-outcome grid (0..N)
    CANDIDATE_SCORE_MAX: int = 5                  # candidate predictions (0..N)

    # V2 de-vig configuration
    V2_DEVIG_METHOD: str = "auto"                 # auto|proportional|power|shin|odds_ratio|exchange_mid
    V2_DEFAULT_AUTO_DEVIG: str = "power"
    V2_FALLBACK_DEVIG: str = "proportional"

    # Export
    EXPORT_DIR: str = "/app/exports"

    # App version
    VERSION: str = "0.1.0"


settings = Settings()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .core.config import settings
from .core.logging import setup_logging
from .api import auth, health, matches, odds, pool_configs, model_runs, exports


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # Ensure the database schema exists. The project ships without Alembic
    # migration *versions*, so `alembic upgrade head` is a no-op and cannot be
    # relied on to create tables. create_all is idempotent (only missing tables
    # are created) and makes the app self-healing on a fresh database.
    try:
        from .db import models  # noqa: F401 - register models on the metadata
        from .db.session import create_all_tables
        await create_all_tables()
    except Exception as exc:  # pragma: no cover - log and keep serving
        from .core.logging import logger
        logger.error("startup: create_all_tables failed", error=str(exc))
    yield


app = FastAPI(title="World Cup Pool Optimizer", version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_BASE_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(pool_configs.router, prefix="/api/pool-configs", tags=["pool-configs"])
app.include_router(matches.router, prefix="/api", tags=["matches"])
app.include_router(odds.router, prefix="/api", tags=["odds"])
app.include_router(model_runs.router, prefix="/api", tags=["model-runs"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])

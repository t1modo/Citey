"""
Citey API — main FastAPI application entrypoint.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, chat, health, jobs, notifications, profile, works

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan: start / stop the background scheduler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start APScheduler on startup (local dev only) and shut it down on teardown.

    In production on Cloud Run, DISABLE_SCHEDULER=true so APScheduler never
    starts — Cloud Scheduler calls the /jobs/* HTTP endpoints instead.
    """
    from app.firebase_client import get_db
    from app.services import email_service

    db = get_db()
    app.state.db = db

    if not settings.disable_scheduler:
        from app.scheduler.jobs import create_scheduler

        scheduler = create_scheduler(
            db=db,
            email_service=email_service,
            settings=settings,
        )
        scheduler.start()
        logger.info("APScheduler started.")
        app.state.scheduler = scheduler
    else:
        logger.info(
            "APScheduler disabled (DISABLE_SCHEDULER=true); "
            "Cloud Scheduler will call /jobs/* HTTP endpoints."
        )

    yield

    if not settings.disable_scheduler and hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    _settings = get_settings()

    application = FastAPI(
        title="Citey API",
        version="0.1.0",
        description=(
            "Backend API for Citey — a citation notification service that alerts "
            "researchers when their published works are cited."
        ),
        lifespan=lifespan,
    )

    # ---- CORS ----------------------------------------------------------------
    raw_origins = _settings.allowed_origins.strip()
    if raw_origins == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers -------------------------------------------------------------
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(profile.router)
    application.include_router(works.router)
    application.include_router(notifications.router)
    application.include_router(jobs.router)
    application.include_router(chat.router)

    # ---- Root (Render health check hits "/" by default) ----------------------
    @application.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"status": "ok"}

    return application


app = create_app()


# ---------------------------------------------------------------------------
# Development entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

"""
Citey API — main FastAPI application entrypoint.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.routers import chat, health, jobs, notifications, profile, works

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
    """Start APScheduler on startup and shut it down cleanly on teardown."""
    from app.firebase_client import get_db
    from app.scheduler.jobs import create_scheduler
    from app.services import email_service

    db = get_db()
    scheduler = create_scheduler(
        db=db,
        email_service=email_service,
        settings=settings,
    )
    scheduler.start()
    logger.info("APScheduler started.")

    # Store on app.state so it can be accessed from tests/routes if needed.
    app.state.scheduler = scheduler
    app.state.db = db

    yield

    scheduler.shutdown(wait=False)
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
    application.include_router(profile.router)
    application.include_router(works.router)
    application.include_router(notifications.router)
    application.include_router(jobs.router)
    application.include_router(chat.router)

    # ---- Root redirect -------------------------------------------------------
    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/health")

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

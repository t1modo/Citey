"""
Citey API — main FastAPI application entrypoint.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import API_PREFIX, get_settings
from app.routers import auth, chat, health, jobs, notifications, profile, support, works

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

if settings.cron_secret_is_default and not settings.is_local:
    logger.error(
        "CRON_SECRET is unset or 'changeme'. Scheduled job endpoints will refuse "
        "requests until a strong secret is configured."
    )
if not settings.token_secret and not settings.is_local:
    logger.warning(
        "TOKEN_SECRET is unset; unsubscribe/RSS links are signed with CRON_SECRET. "
        "Set a dedicated TOKEN_SECRET."
    )


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
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # ---- Old paths -------------------------------------------------------------
    # Routes used to live at the root (/profile, /jobs/run, ...). Links in
    # emails already sent, and a site build still pointing at the old base,
    # use those paths, so they are redirected to /api. 308 keeps the method
    # and body. Registered before CORS so CORS stays the outer layer: it
    # answers preflights itself and adds its headers to the redirect.
    @application.middleware("http")
    async def redirect_unprefixed(request: Request, call_next):
        path = request.url.path
        if path != "/" and path != API_PREFIX and not path.startswith(f"{API_PREFIX}/"):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"{API_PREFIX}{path}{query}", status_code=308)
        return await call_next(request)

    # ---- CORS ----------------------------------------------------------------
    raw_origins = _settings.allowed_origins.strip()
    if raw_origins == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Auth uses a Bearer header, not cookies, so credentialed CORS is
        # unnecessary (and unsafe combined with a wildcard origin).
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers -------------------------------------------------------------
    for module in (health, auth, profile, works, notifications, jobs, chat, support):
        application.include_router(module.router, prefix=API_PREFIX)

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

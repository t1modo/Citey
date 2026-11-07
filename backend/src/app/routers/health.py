import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/health/db")
async def database_health_check():
    """Neon Postgres: connect, write and read back in a rolled back transaction."""
    from app.core import db

    try:
        result = await asyncio.to_thread(db.check)
    except db.DatabaseNotConfigured:
        return JSONResponse({"status": "not_configured"}, status_code=503)
    except Exception as exc:  # noqa: BLE001
        # Never echo the error: it can include the connection string's host.
        logger.error("Database health check failed: %s", type(exc).__name__)
        return JSONResponse({"status": "error"}, status_code=503)
    status = "ok" if result["write_read_ok"] else "error"
    return JSONResponse({"status": status, **result}, status_code=200 if status == "ok" else 503)

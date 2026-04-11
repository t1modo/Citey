"""
APScheduler configuration for local development.

In production you would replace this with a cron trigger (e.g. Cloud Scheduler
hitting the /jobs/run endpoint).  For local dev, this module spins up a
BackgroundScheduler that fires run_job_for_all_users at a configurable interval.
"""

import asyncio
import logging
from types import ModuleType
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Settings
from app.services.citation_service import run_job_for_all_users
from app.services.publication_sync import sync_new_publications_for_all_users

logger = logging.getLogger(__name__)


def _make_job_func(db: Any, email_service: ModuleType, settings: Settings):
    """
    Return a plain (non-async) callable that APScheduler can call.

    APScheduler's BackgroundScheduler does not natively support coroutine
    functions, so we wrap the async job in a new event loop.
    """

    def _run_job() -> None:
        logger.info("APScheduler: starting scheduled citation-check job.")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                summary = loop.run_until_complete(
                    run_job_for_all_users(
                        db=db,
                        email_service=email_service,
                        dry_run=False,
                        settings=settings,
                    )
                )
                logger.info("APScheduler: job finished — %s", summary)
            finally:
                loop.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("APScheduler: job raised an exception: %s", exc, exc_info=True)

    return _run_job


def _make_pub_sync_func(db: Any, email_service: ModuleType, settings: Settings):
    """Return a plain callable for the weekly publication-sync job."""

    def _run_pub_sync() -> None:
        logger.info("APScheduler: starting scheduled publication-sync job.")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                summary = loop.run_until_complete(
                    sync_new_publications_for_all_users(
                        db=db,
                        email_service=email_service,
                        dry_run=False,
                        settings=settings,
                    )
                )
                logger.info("APScheduler: publication-sync finished — %s", summary)
            finally:
                loop.close()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "APScheduler: publication-sync raised an exception: %s", exc, exc_info=True
            )

    return _run_pub_sync


def create_scheduler(
    db: Any,
    email_service: ModuleType,
    settings: Settings,
) -> BackgroundScheduler:
    """
    Create and configure an APScheduler BackgroundScheduler.

    citation_check runs at a configurable interval (default every 24 hours)
    to discover new citing papers, store Notification documents, and send
    an immediate email to the user if new citations were found.

    publication_sync runs weekly (every 7 days) to detect new publications
    on the user's linked OpenAlex author profile and auto-add them.

    The returned scheduler is *not* started; the caller (lifespan context in
    main.py) is responsible for calling ``scheduler.start()`` and
    ``scheduler.shutdown()``.
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    interval_hours = max(1, settings.scheduler_interval_hours)
    scheduler.add_job(
        func=_make_job_func(db=db, email_service=email_service, settings=settings),
        trigger="interval",
        hours=interval_hours,
        id="citation_check",
        name="Citation Check",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        func=_make_pub_sync_func(db=db, email_service=email_service, settings=settings),
        trigger="interval",
        weeks=1,
        id="publication_sync",
        name="Publication Sync",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler configured: citation_check every %d hour(s), publication_sync weekly.",
        interval_hours,
    )
    return scheduler

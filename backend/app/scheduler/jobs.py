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
from app.services.citation_service import cleanup_old_notifications, run_job_for_all_users
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


def _make_cleanup_func(db: Any):
    """Return a plain callable for the daily notification-cleanup job."""

    def _run_cleanup() -> None:
        logger.info("APScheduler: starting scheduled notification-cleanup job.")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                summary = loop.run_until_complete(
                    cleanup_old_notifications(db=db, dry_run=False)
                )
                logger.info("APScheduler: notification-cleanup finished — %s", summary)
            finally:
                loop.close()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "APScheduler: notification-cleanup raised an exception: %s", exc, exc_info=True
            )

    return _run_cleanup


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
    # All jobs run on a fixed PST schedule (UTC-8 / UTC-7 during DST).
    # Using pytz "America/Los_Angeles" lets APScheduler handle DST automatically.
    scheduler = BackgroundScheduler(timezone="America/Los_Angeles")

    # Citation check: every day at 00:00 PST
    scheduler.add_job(
        func=_make_job_func(db=db, email_service=email_service, settings=settings),
        trigger="cron",
        hour=0,
        minute=0,
        id="citation_check",
        name="Citation Check",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Publication sync: every Sunday at 00:30 PST (offset slightly to avoid overlap)
    scheduler.add_job(
        func=_make_pub_sync_func(db=db, email_service=email_service, settings=settings),
        trigger="cron",
        day_of_week="sun",
        hour=0,
        minute=30,
        id="publication_sync",
        name="Publication Sync",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Notification cleanup: every day at 01:00 PST (after citation check completes)
    scheduler.add_job(
        func=_make_cleanup_func(db=db),
        trigger="cron",
        hour=1,
        minute=0,
        id="notification_cleanup",
        name="Notification Cleanup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler configured: citation_check daily at 00:00 PST, "
        "publication_sync weekly (Sun 00:30 PST), notification_cleanup daily at 01:00 PST.",
    )
    return scheduler

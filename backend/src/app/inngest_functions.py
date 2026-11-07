"""
Scheduled jobs, run by Inngest.

Inngest calls /api/inngest on a schedule and for every event below; each
call runs one step and returns. Steps are kept short so each one fits a
single request (Vercel Hobby stops a request after 300 s):

* Nightly citation check, 00:00 Pacific. A sweep lists the users and sends
  one event per user; each event runs one user's check as its own run, with
  its own retries.
* Notification cleanup, 01:00 Pacific. Deletes notifications older than 30
  days, the same single pass /api/jobs/cleanup-notifications makes.
* Weekly publication sync, Sunday 00:00 Pacific. Fanned out per user like
  the citation check, for users with a linked OpenAlex author.

The schedules use TZ= crons, so midnight stays midnight across daylight
saving time. Midnight and 01:00 are clear of the 02:00 US DST switch.
"""

import logging
import time
from datetime import datetime, timezone

import inngest
import inngest.fast_api
import pytz
from fastapi import FastAPI

from app.config import API_PREFIX, Settings, get_settings
from app.core.db import session_scope
from app.services import email_service
from app.services.citation_service import (
    _get_auth_uids,
    cleanup_old_notifications,
    run_job_for_user,
)
from app.services.publication_sync import sync_new_publications_for_user
from app.store import UserStore

logger = logging.getLogger(__name__)

APP_ID = "citey"
SERVE_PATH = f"{API_PREFIX}/inngest"
PACIFIC = "America/Los_Angeles"

NIGHTLY_CRON = f"TZ={PACIFIC} 0 0 * * *"
CLEANUP_CRON = f"TZ={PACIFIC} 0 1 * * *"
WEEKLY_CRON = f"TZ={PACIFIC} 0 0 * * 0"

CITATION_CHECK_EVENT = "citey/citation-check.requested"
PUBLICATION_SYNC_EVENT = "citey/publication-sync.requested"

# Per-user runs that may be checking at once, shared by the citation check
# and the publication sync (both start at midnight on Sundays). The old
# sweep checked one user at a time; two keeps OpenAlex and Semantic Scholar
# well inside their limits while halving the night's wall time.
SOURCES_CONCURRENCY = 2
_SOURCES_LIMIT = inngest.Concurrency(scope="env", key='"citey-sources"', limit=SOURCES_CONCURRENCY)
# Never two runs for one user at once: two checks could both find a
# citation before either records it, and email it twice.
_ONE_PER_USER = inngest.Concurrency(key="event.data.uid", limit=1)

# Events sent per step when fanning out; keeps each Event API request small.
FAN_OUT_CHUNK = 100

USER_RETRIES = 3
SWEEP_RETRIES = 3

# A user's check runs as a series of steps, each one request. A step starts
# no new paper after this many seconds, leaving room under Vercel Hobby's
# 300 s limit for the paper in progress, the count refresh and the email.
# The next step skips papers already checked in this run.
PART_BUDGET_SECONDS = 200.0
MAX_PARTS = 20


def _is_dev(value: str) -> bool:
    return value.strip().lower() not in ("", "0", "false")


def create_client(settings: Settings | None = None) -> inngest.Inngest:
    """The Inngest client, configured from Settings so backend/.env works.

    INNGEST_DEV=1 talks to a Dev Server on localhost:8288 (or at
    INNGEST_BASE_URL); INNGEST_DEV=<url> talks to the Dev Server at that URL.
    Otherwise the client is in production (cloud) mode.
    """
    settings = settings or get_settings()
    dev = settings.inngest_dev.strip()
    dev_url = dev if _is_dev(dev) and "://" in dev else None
    return inngest.Inngest(
        app_id=APP_ID,
        logger=logging.getLogger("citey.inngest"),
        is_production=not _is_dev(dev),
        signing_key=settings.inngest_signing_key or None,
        event_key=settings.inngest_event_key or None,
        api_base_url=dev_url,
        event_api_base_url=dev_url,
    )


inngest_client = create_client()


def _pacific_date() -> str:
    return datetime.now(pytz.timezone(PACIFIC)).date().isoformat()


# ---------------------------------------------------------------------------
# Work done inside steps. Each opens its own database session.
# ---------------------------------------------------------------------------


async def list_citation_check_uids() -> list[str]:
    """Every user with a Firebase Auth account, in uid order (accounts with
    no sign-in record are skipped, as the all-users sweep does)."""
    auth_uids = await _get_auth_uids()
    async with session_scope() as session:
        all_uids = await UserStore(session).ids_after()
    uids = []
    for uid in all_uids:
        if uid not in auth_uids:
            logger.warning("Skipping user uid=%s with no sign-in account in citation sweep", uid)
            continue
        uids.append(uid)
    return uids


async def list_publication_sync_uids() -> list[str]:
    """Users with an Auth account and a linked OpenAlex author, in uid order.

    Semantic Scholar links ("S2:...") are left out: the sync skips them.
    """
    auth_uids = await _get_auth_uids()
    uids = []
    async with session_scope() as session:
        store = UserStore(session)
        for uid in await store.ids_after():
            if uid not in auth_uids:
                logger.warning("Skipping user uid=%s with no sign-in account in publication sweep", uid)
                continue
            user = await store.get(uid)
            author = user.linked_author_id if user else None
            if author and not str(author).startswith("S2:"):
                uids.append(uid)
    return uids


async def check_user_citations(
    uid: str,
    dry_run: bool = False,
    checked_since: str | None = None,
    time_budget_seconds: float | None = None,
) -> dict:
    """One part of a user's check. ``done`` is False when the time budget ran
    out with papers left; the next part, given the same *checked_since*,
    carries on from there."""
    async with session_scope() as session:
        if await UserStore(session).get(uid) is None:
            logger.info("Skipping citation check for uid=%s: user is gone.", uid)
            return {"uid": uid, "skipped": "no user document", "done": True}
        stats: dict[str, int] = {}
        works_processed, new_notifications = await run_job_for_user(
            uid=uid,
            session=session,
            email_service=email_service,
            dry_run=dry_run,
            settings=get_settings(),
            stats=stats,
            deadline=(time.monotonic() + time_budget_seconds) if time_budget_seconds else None,
            checked_since=datetime.fromisoformat(checked_since) if checked_since else None,
        )
    return {
        "uid": uid,
        "works_processed": works_processed,
        "new_notifications": new_notifications,
        "done": not stats.get("incomplete"),
    }


async def sync_user_publications(uid: str, dry_run: bool = False) -> dict:
    async with session_scope() as session:
        user = await UserStore(session).get(uid)
        if user is None or not user.linked_author_id:
            return {"uid": uid, "skipped": "no linked author"}
        added = await sync_new_publications_for_user(
            uid=uid,
            session=session,
            email_service=email_service,
            dry_run=dry_run,
            settings=get_settings(),
        )
    return {"uid": uid, "works_added": added}


async def cleanup_notifications() -> dict:
    async with session_scope() as session:
        return await cleanup_old_notifications(session=session, dry_run=False)


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------


def fan_out_events(name: str, kind: str, day: str, uids: list[str]) -> list[inngest.Event]:
    """One event per user. The ID makes a repeat for the same user and day a
    no-op (Inngest ignores a duplicate event ID for 24 hours), so a second
    sweep the same night, run by hand or by a retry, emails nobody twice."""
    return [
        inngest.Event(name=name, id=f"{kind}-{day}-{uid}", data={"uid": uid})
        for uid in uids
    ]


async def _sweep(ctx: inngest.Context, list_step: str, list_uids, event: str, kind: str) -> dict:
    async def plan() -> dict:
        return {"day": _pacific_date(), "uids": await list_uids()}

    planned = await ctx.step.run(list_step, plan)
    day, uids = planned["day"], planned["uids"]
    for i in range(0, len(uids), FAN_OUT_CHUNK):
        await ctx.step.send_event(
            f"fan-out-{i // FAN_OUT_CHUNK}",
            fan_out_events(event, kind, day, uids[i : i + FAN_OUT_CHUNK]),
        )
    ctx.logger.info("%s sweep for %s: %d user(s) queued.", kind, day, len(uids))
    return {"day": day, "users_queued": len(uids)}


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


@inngest_client.create_function(
    fn_id="nightly-citation-sweep",
    name="Nightly citation check",
    trigger=inngest.TriggerCron(cron=NIGHTLY_CRON),
    # One sweep at a time; a second one started while it runs is skipped.
    singleton=inngest.Singleton(mode="skip"),
    retries=SWEEP_RETRIES,
)
async def nightly_citation_sweep(ctx: inngest.Context) -> dict:
    return await _sweep(
        ctx, "list-users", list_citation_check_uids, CITATION_CHECK_EVENT, "citation-check"
    )


@inngest_client.create_function(
    fn_id="citation-check-user",
    name="Citation check for one user",
    trigger=inngest.TriggerEvent(event=CITATION_CHECK_EVENT),
    concurrency=[_SOURCES_LIMIT, _ONE_PER_USER],
    retries=USER_RETRIES,
)
async def citation_check_user(ctx: inngest.Context) -> dict:
    uid = str(ctx.event.data["uid"])
    dry_run = bool(ctx.event.data.get("dry_run", False))

    async def started_at() -> str:
        return datetime.now(timezone.utc).isoformat()

    # Recorded once and replayed on every later request of this run, so each
    # part skips the papers earlier parts checked.
    since = await ctx.step.run("start", started_at)

    totals = {"uid": uid, "works_processed": 0, "new_notifications": 0}
    # A dry run records nothing, so a later part could not tell which
    # papers were done; it checks what fits in one part.
    parts = 1 if dry_run else MAX_PARTS
    for part in range(parts):
        async def check(part: int = part) -> dict:
            return await check_user_citations(
                uid=uid,
                dry_run=dry_run,
                checked_since=since,
                time_budget_seconds=PART_BUDGET_SECONDS,
            )

        result = await ctx.step.run("check-citations" if part == 0 else f"check-citations-{part}", check)
        if "skipped" in result:
            return {k: v for k, v in result.items() if k != "done"}
        totals["works_processed"] += result["works_processed"]
        totals["new_notifications"] += result["new_notifications"]
        if result.get("done", True):
            return totals
    ctx.logger.warning("uid=%s still had papers left after %d parts.", uid, parts)
    return {**totals, "unfinished": True}


@inngest_client.create_function(
    fn_id="notification-cleanup",
    name="Notification cleanup",
    trigger=inngest.TriggerCron(cron=CLEANUP_CRON),
    singleton=inngest.Singleton(mode="skip"),
    retries=SWEEP_RETRIES,
)
async def notification_cleanup(ctx: inngest.Context) -> dict:
    async def cleanup() -> dict:
        return await cleanup_notifications()

    return await ctx.step.run("delete-old-notifications", cleanup)


@inngest_client.create_function(
    fn_id="weekly-publication-sweep",
    name="Weekly publication sync",
    trigger=inngest.TriggerCron(cron=WEEKLY_CRON),
    singleton=inngest.Singleton(mode="skip"),
    retries=SWEEP_RETRIES,
)
async def weekly_publication_sweep(ctx: inngest.Context) -> dict:
    return await _sweep(
        ctx, "list-linked-users", list_publication_sync_uids, PUBLICATION_SYNC_EVENT, "publication-sync"
    )


@inngest_client.create_function(
    fn_id="publication-sync-user",
    name="Publication sync for one user",
    trigger=inngest.TriggerEvent(event=PUBLICATION_SYNC_EVENT),
    concurrency=[_SOURCES_LIMIT, _ONE_PER_USER],
    retries=USER_RETRIES,
)
async def publication_sync_user(ctx: inngest.Context) -> dict:
    uid = str(ctx.event.data["uid"])
    dry_run = bool(ctx.event.data.get("dry_run", False))

    async def sync() -> dict:
        return await sync_user_publications(uid=uid, dry_run=dry_run)

    return await ctx.step.run("sync-publications", sync)


FUNCTIONS = [
    nightly_citation_sweep,
    citation_check_user,
    notification_cleanup,
    weekly_publication_sweep,
    publication_sync_user,
]


def serve(app: FastAPI, client: inngest.Inngest | None = None) -> bool:
    """Mount the Inngest endpoint at /api/inngest.

    In production mode without a signing key the SDK cannot verify Inngest's
    requests and refuses to start, so the endpoint is left out (the rest of
    the API keeps working) and the scheduled jobs do not run until the key
    is set.
    """
    client = client or inngest_client
    if client.is_production and not client.signing_key:
        log = logger.warning if get_settings().is_local else logger.error
        log(
            "INNGEST_SIGNING_KEY is unset: %s is not served and the scheduled "
            "jobs will not run. Set it, or INNGEST_DEV=1 for a local Dev Server.",
            SERVE_PATH,
        )
        return False
    inngest.fast_api.serve(app, client, FUNCTIONS, serve_path=SERVE_PATH)
    return True

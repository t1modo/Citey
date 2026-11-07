"""The Inngest functions that run the nightly and weekly jobs.

Runs use the SDK's in-memory simulator (inngest.experimental.mocked), so no
Inngest server or network is involved. Tests that read or write users,
papers or alerts use the test database (marked ``needs_db``; set
TEST_DATABASE_URL, see tests/conftest.py); the rest need none.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import inngest
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inngest.experimental import mocked
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import inngest_functions as fns
from app.config import Settings
from app.models import Alert
from app.services import tracking_service
from app.store import AlertStore, CitationStore, UserStore
from tests.conftest import TEST_DATABASE_URL, needs_db


class _RecordingClient(mocked.Inngest):
    """Mock client that keeps the events step.send_event sends."""

    def __init__(self) -> None:
        super().__init__(app_id="test")
        self.sent: list[inngest.Event] = []

    async def send(self, events, *, skip_middleware: bool = False) -> list[str]:
        events = events if isinstance(events, list) else [events]
        self.sent.extend(events)
        return await super().send(events, skip_middleware=skip_middleware)


@pytest.fixture(autouse=True)
def _no_inngest_env(monkeypatch: pytest.MonkeyPatch):
    """The SDK falls back to INNGEST_* env vars; keep the shell's out."""
    for key in ("INNGEST_DEV", "INNGEST_SIGNING_KEY", "INNGEST_EVENT_KEY", "INNGEST_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
async def app_db(pg_session, monkeypatch: pytest.MonkeyPatch):
    """Point the functions' own sessions at the test database.

    The step helpers open sessions with app.core.db.session_scope(). That is
    left real; only the URL its cached engine is built from changes. Patching
    session_scope to hand out pg_session would not work here: a run happens
    on another thread's event loop (see _trigger), and a session's
    connection belongs to the loop that opened it. Seed and inspect through
    the returned pg_session, and commit before a run, which reads over its
    own connection.
    """
    from app.core import db as core_db

    monkeypatch.setattr(core_db, "get_settings", lambda: Settings(database_url=TEST_DATABASE_URL))
    core_db.get_engine.cache_clear()
    yield pg_session
    core_db.get_engine.cache_clear()


@pytest.fixture
def seed(app_db, monkeypatch: pytest.MonkeyPatch):
    """Create user rows (uid -> column values) and the Clerk
    accounts; by default every seeded user has one."""

    async def install(users: dict[str, dict] | None = None, *, auth_uids: set[str] | None = None) -> None:
        users = users or {}
        for uid, fields in users.items():
            await UserStore(app_db).create(uid, email=f"{uid}@example.com", **fields)
        await app_db.commit()
        uids = set(users) if auth_uids is None else auth_uids
        monkeypatch.setattr(fns, "_get_auth_uids", AsyncMock(return_value=set(uids)))

    return install


async def _trigger(fn: inngest.Function, event: inngest.Event, client: mocked.Inngest):
    """mocked.trigger drives an event loop of its own (run_until_complete),
    which cannot happen inside the test's running loop, so the run goes on a
    worker thread, where the SDK makes a fresh loop."""
    return await asyncio.to_thread(mocked.trigger, fn, event, client)


def _cron_event() -> inngest.Event:
    return inngest.Event(name="inngest/scheduled.timer")


def _user_event(name: str, uid: str, **data) -> inngest.Event:
    return inngest.Event(name=name, data={"uid": uid, **data})


# ---------------------------------------------------------------------------
# Schedules and flow control
# ---------------------------------------------------------------------------


def _config(fn: inngest.Function):
    """What the SDK registers with Inngest for *fn*."""
    return fn.get_config("http://test/api/inngest").main


def _triggers(fn: inngest.Function) -> list:
    return _config(fn).triggers


@pytest.mark.parametrize(
    ("fn", "cron"),
    [
        (fns.nightly_citation_sweep, "TZ=America/Los_Angeles 0 0 * * *"),
        (fns.notification_cleanup, "TZ=America/Los_Angeles 0 1 * * *"),
        (fns.weekly_publication_sweep, "TZ=America/Los_Angeles 0 0 * * 0"),
    ],
)
def test_crons_run_on_pacific_time(fn, cron):
    [trigger] = _triggers(fn)
    assert isinstance(trigger, inngest.TriggerCron)
    assert trigger.cron == cron


@pytest.mark.parametrize(
    ("fn", "event"),
    [
        (fns.citation_check_user, fns.CITATION_CHECK_EVENT),
        (fns.publication_sync_user, fns.PUBLICATION_SYNC_EVENT),
    ],
)
def test_per_user_functions_are_event_triggered(fn, event):
    [trigger] = _triggers(fn)
    assert isinstance(trigger, inngest.TriggerEvent)
    assert trigger.event == event


@pytest.mark.parametrize("fn", [fns.citation_check_user, fns.publication_sync_user])
def test_per_user_runs_share_a_source_limit_and_never_overlap_for_one_user(fn):
    config = _config(fn)
    limits = config.concurrency
    assert inngest.Concurrency(scope="env", key='"citey-sources"', limit=fns.SOURCES_CONCURRENCY) in limits
    assert inngest.Concurrency(key="event.data.uid", limit=1) in limits
    [step] = config.steps.values()
    assert step.retries.attempts == fns.USER_RETRIES > 0


@pytest.mark.parametrize(
    "fn", [fns.nightly_citation_sweep, fns.notification_cleanup, fns.weekly_publication_sweep]
)
def test_scheduled_sweeps_are_singletons(fn):
    config = _config(fn)
    assert config.singleton == inngest.Singleton(mode="skip")
    assert config.concurrency is None  # the docs advise against mixing the two


def test_every_function_is_served():
    ids = {fn.id for fn in fns.FUNCTIONS}
    assert ids == {
        "citey-nightly-citation-sweep",
        "citey-citation-check-user",
        "citey-notification-cleanup",
        "citey-weekly-publication-sweep",
        "citey-publication-sync-user",
    }


# ---------------------------------------------------------------------------
# Nightly citation sweep
# ---------------------------------------------------------------------------


@needs_db
async def test_citation_sweep_sends_one_event_per_user(seed, monkeypatch):
    await seed({"b": {}, "a": {}, "c": {}})
    monkeypatch.setattr(fns, "_pacific_date", lambda: "2026-11-06")
    client = _RecordingClient()

    res = await _trigger(fns.nightly_citation_sweep, _cron_event(), client)

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"day": "2026-11-06", "users_queued": 3}
    assert [(e.name, e.id, e.data) for e in client.sent] == [
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-a", {"uid": "a"}),
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-b", {"uid": "b"}),
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-c", {"uid": "c"}),
    ]


@needs_db
async def test_citation_sweep_skips_orphaned_users(seed):
    await seed({"a": {}, "orphan": {}, "b": {}}, auth_uids={"a", "b"})
    client = _RecordingClient()

    await _trigger(fns.nightly_citation_sweep, _cron_event(), client)

    assert [e.data["uid"] for e in client.sent] == ["a", "b"]


@needs_db
async def test_citation_sweep_sends_large_lists_in_chunks(seed, monkeypatch):
    monkeypatch.setattr(fns, "FAN_OUT_CHUNK", 2)
    await seed({f"u{i}": {} for i in range(5)})
    client = _RecordingClient()
    sends = []
    original = client.send

    async def counting_send(events, *, skip_middleware=False):
        sends.append(len(events))
        return await original(events, skip_middleware=skip_middleware)

    client.send = counting_send

    res = await _trigger(fns.nightly_citation_sweep, _cron_event(), client)

    assert res.output["users_queued"] == 5
    assert sends == [2, 2, 1]
    assert len({e.id for e in client.sent}) == 5


def test_event_ids_repeat_for_the_same_user_and_day():
    """A second sweep the same night produces the same event IDs, which
    Inngest drops as duplicates, so nobody is checked or emailed twice."""
    first = fns.fan_out_events(fns.CITATION_CHECK_EVENT, "citation-check", "2026-11-06", ["a"])
    again = fns.fan_out_events(fns.CITATION_CHECK_EVENT, "citation-check", "2026-11-06", ["a"])
    tomorrow = fns.fan_out_events(fns.CITATION_CHECK_EVENT, "citation-check", "2026-11-07", ["a"])
    assert first[0].id == again[0].id != tomorrow[0].id


# ---------------------------------------------------------------------------
# Per-user citation check
# ---------------------------------------------------------------------------


@needs_db
async def test_user_check_calls_run_job_for_user(seed, monkeypatch):
    """The check runs in a session of its own on the user's row, with this
    part's deadline and the run's start time."""
    await seed({"a": {"display_name": "Ada"}})
    seen: dict = {}

    async def fake_run(**kwargs):
        seen["display_name"] = (await UserStore(kwargs["session"]).get("a")).display_name
        return 4, 2

    run = AsyncMock(side_effect=fake_run)
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = await _trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_processed": 4, "new_notifications": 2}
    run.assert_awaited_once()
    kwargs = run.await_args.kwargs
    assert kwargs["uid"] == "a"
    assert isinstance(kwargs["session"], AsyncSession)
    assert seen["display_name"] == "Ada"
    assert kwargs["email_service"] is fns.email_service
    assert kwargs["dry_run"] is False
    assert isinstance(kwargs["checked_since"], datetime)
    assert kwargs["deadline"] is not None


@needs_db
async def test_user_check_passes_dry_run_through(seed, monkeypatch):
    await seed({"a": {}})
    run = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr(fns, "run_job_for_user", run)

    await _trigger(
        fns.citation_check_user,
        _user_event(fns.CITATION_CHECK_EVENT, "a", dry_run=True),
        _RecordingClient(),
    )

    assert run.await_args.kwargs["dry_run"] is True


@needs_db
async def test_user_check_skips_a_deleted_user(seed, monkeypatch):
    await seed()
    run = AsyncMock()
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = await _trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "gone"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "gone", "skipped": "no user document"}
    run.assert_not_awaited()


@needs_db
async def test_user_check_is_retried_on_failure(seed, monkeypatch):
    await seed({"a": {}})
    run = AsyncMock(side_effect=[RuntimeError("database timeout"), (3, 1)])
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = await _trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output["new_notifications"] == 1
    assert run.await_count == 2


@needs_db
async def test_user_check_fails_after_its_retries(seed, monkeypatch):
    await seed({"a": {}})
    run = AsyncMock(side_effect=RuntimeError("down"))
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = await _trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.FAILED
    assert run.await_count == fns.USER_RETRIES + 1


@needs_db
async def test_a_part_that_runs_out_of_time_reports_not_done(seed, monkeypatch):
    """One part's step: run_job_for_user's "incomplete" becomes done=False,
    the part's budget becomes its deadline and the run start is parsed back."""
    await seed({"a": {}})
    calls: list[dict] = []

    async def out_of_time(**kwargs):
        calls.append(kwargs)
        kwargs["stats"]["incomplete"] = 1
        return 5, 1

    monkeypatch.setattr(fns, "run_job_for_user", out_of_time)
    since = "2026-11-06T08:00:00+00:00"

    before = time.monotonic()
    result = await fns.check_user_citations("a", checked_since=since, time_budget_seconds=200)

    assert result == {"uid": "a", "works_processed": 5, "new_notifications": 1, "done": False}
    [kwargs] = calls
    assert kwargs["checked_since"] == datetime(2026, 11, 6, 8, tzinfo=timezone.utc)
    assert before + 199 < kwargs["deadline"] < time.monotonic() + 201


def test_a_long_user_check_continues_in_more_parts(monkeypatch):
    """Each part is one request; a user who outlasts it carries on in the
    next part, skipping papers checked since the run started."""
    calls: list[dict] = []

    async def fake_check(**kwargs):
        calls.append(kwargs)
        return {"uid": "a", "works_processed": 5, "new_notifications": 1, "done": len(calls) >= 3}

    monkeypatch.setattr(fns, "check_user_citations", fake_check)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_processed": 15, "new_notifications": 3}
    assert len(calls) == 3
    since = {c["checked_since"] for c in calls}
    assert len(since) == 1 and None not in since  # one run start, shared by every part
    assert all(c["time_budget_seconds"] == fns.PART_BUDGET_SECONDS for c in calls)


def test_a_user_check_gives_up_after_its_part_limit(monkeypatch):
    async def never_done(**kwargs):
        return {"uid": "a", "works_processed": 1, "new_notifications": 0, "done": False}

    monkeypatch.setattr(fns, "check_user_citations", never_done)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output["unfinished"] is True
    assert res.output["works_processed"] == fns.MAX_PARTS


def test_a_dry_run_user_check_is_one_part(monkeypatch):
    check = AsyncMock(return_value={"uid": "a", "works_processed": 1, "new_notifications": 0, "done": False})
    monkeypatch.setattr(fns, "check_user_citations", check)

    mocked.trigger(
        fns.citation_check_user,
        _user_event(fns.CITATION_CHECK_EVENT, "a", dry_run=True),
        _RecordingClient(),
    )

    assert check.await_count == 1
    assert check.await_args.kwargs["dry_run"] is True


# ---------------------------------------------------------------------------
# Weekly publication sync
# ---------------------------------------------------------------------------


@needs_db
async def test_publication_sweep_only_queues_users_with_a_linked_author(seed, monkeypatch):
    await seed(
        {
            "a": {"linked_author_id": "A123"},
            "b": {},
            "c": {"linked_author_id": ""},
            "d": {"linked_author_id": "S2:999"},
            "e": {"linked_author_id": "A456"},
            "orphan": {"linked_author_id": "A789"},
        },
        auth_uids={"a", "b", "c", "d", "e"},
    )
    monkeypatch.setattr(fns, "_pacific_date", lambda: "2026-11-08")
    client = _RecordingClient()

    res = await _trigger(fns.weekly_publication_sweep, _cron_event(), client)

    assert res.output == {"day": "2026-11-08", "users_queued": 2}
    assert [(e.name, e.id, e.data) for e in client.sent] == [
        (fns.PUBLICATION_SYNC_EVENT, "publication-sync-2026-11-08-a", {"uid": "a"}),
        (fns.PUBLICATION_SYNC_EVENT, "publication-sync-2026-11-08-e", {"uid": "e"}),
    ]


@needs_db
async def test_user_sync_calls_sync_new_publications_for_user(seed, monkeypatch):
    """The sync runs in a session of its own that sees the user's row."""
    await seed({"a": {"linked_author_id": "A123"}})
    seen: dict = {}

    async def fake_sync(**kwargs):
        seen["linked_author_id"] = (await UserStore(kwargs["session"]).get("a")).linked_author_id
        return 3

    sync = AsyncMock(side_effect=fake_sync)
    monkeypatch.setattr(fns, "sync_new_publications_for_user", sync)

    res = await _trigger(
        fns.publication_sync_user, _user_event(fns.PUBLICATION_SYNC_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_added": 3}
    kwargs = sync.await_args.kwargs
    assert kwargs["uid"] == "a"
    assert isinstance(kwargs["session"], AsyncSession)
    assert seen["linked_author_id"] == "A123"
    assert kwargs["email_service"] is fns.email_service
    assert kwargs["dry_run"] is False


@needs_db
async def test_user_sync_skips_a_user_who_unlinked_since_the_sweep(seed, monkeypatch):
    await seed({"a": {}})
    sync = AsyncMock()
    monkeypatch.setattr(fns, "sync_new_publications_for_user", sync)

    res = await _trigger(
        fns.publication_sync_user, _user_event(fns.PUBLICATION_SYNC_EVENT, "a"), _RecordingClient()
    )

    assert res.output["skipped"]
    sync.assert_not_awaited()


# ---------------------------------------------------------------------------
# Notification cleanup
# ---------------------------------------------------------------------------


@needs_db
async def test_cleanup_deletes_old_notifications(seed, app_db):
    """Alerts found more than 30 days ago go; newer ones and the citations
    themselves stay."""
    await seed({"a": {}, "b": {}})
    now = datetime.now(timezone.utc)
    work, _ = await tracking_service.track_paper(
        app_db, "a", "10.1__paper", {"doi": "10.1/paper", "title": "A paper"}, now=now - timedelta(days=60)
    )
    for doi, found in (("10.9/old", now - timedelta(days=40)), ("10.9/new", now - timedelta(days=2))):
        cid, _ = await CitationStore(app_db).record(
            work.id, doi, {f"doi:{doi}"}, {"doi": doi, "title": f"Paper {doi}"}, found_at=found
        )
        await AlertStore(app_db).add("a", cid, created_at=found)
    await app_db.commit()

    res = await _trigger(fns.notification_cleanup, _cron_event(), _RecordingClient())

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"users_processed": 2, "notifications_deleted": 1}
    left = (await app_db.exec(select(Alert))).all()
    assert len(left) == 1 and left[0].created_at > now - timedelta(days=30)


# ---------------------------------------------------------------------------
# Client and serving
# ---------------------------------------------------------------------------


def test_client_uses_the_dev_server_when_inngest_dev_is_set():
    client = fns.create_client(Settings(inngest_dev="1"))
    assert not client.is_production


def test_client_takes_a_dev_server_url():
    client = fns.create_client(Settings(inngest_dev="http://inngest:8288"))
    assert not client.is_production
    assert client.api_origin.startswith("http://inngest:8288")
    assert client.event_api_origin.startswith("http://inngest:8288")


def test_client_is_in_production_mode_by_default():
    client = fns.create_client(Settings(inngest_dev="", inngest_signing_key="signkey-prod-abc"))
    assert client.is_production
    assert client.signing_key == "signkey-prod-abc"


def test_serves_the_functions_under_api_prefix():
    app = FastAPI()
    assert fns.serve(app, fns.create_client(Settings(inngest_dev="1"))) is True

    res = TestClient(app).get("/api/inngest")

    assert res.status_code == 200
    assert res.json()["function_count"] == len(fns.FUNCTIONS)


def test_production_without_a_signing_key_leaves_the_endpoint_out():
    app = FastAPI()
    client = fns.create_client(Settings(inngest_dev="", inngest_signing_key=""))
    assert fns.serve(app, client) is False
    assert TestClient(app).get("/api/inngest").status_code == 404

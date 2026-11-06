"""The Inngest functions that run the nightly and weekly jobs.

Runs use the SDK's in-memory simulator (inngest.experimental.mocked), so no
Inngest server, Firestore or network is involved.
"""

import threading
from unittest.mock import AsyncMock, MagicMock

import inngest
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inngest.experimental import mocked

from app import inngest_functions as fns
from app.config import Settings


class _RecordingClient(mocked.Inngest):
    """Mock client that keeps the events step.send_event sends."""

    def __init__(self) -> None:
        super().__init__(app_id="test")
        self.sent: list[inngest.Event] = []

    async def send(self, events, *, skip_middleware: bool = False) -> list[str]:
        events = events if isinstance(events, list) else [events]
        self.sent.extend(events)
        return await super().send(events, skip_middleware=skip_middleware)


def _user(uid: str, **data) -> MagicMock:
    doc = MagicMock()
    doc.id = uid
    doc.to_dict.return_value = data
    return doc


def _db(*users: MagicMock) -> MagicMock:
    """A Firestore stand-in: collection("users") streams *users*, and
    document(uid).get() returns the matching one (or a missing document)."""
    by_id = {u.id: u for u in users}
    db = MagicMock()
    users_ref = db.collection.return_value
    users_ref.stream.return_value = list(users)

    def document(uid):
        ref = MagicMock()
        snapshot = MagicMock()
        snapshot.exists = uid in by_id
        snapshot.to_dict.return_value = by_id[uid].to_dict() if uid in by_id else None
        ref.get.return_value = snapshot
        return ref

    users_ref.document.side_effect = document
    return db


@pytest.fixture(autouse=True)
def _no_inngest_env(monkeypatch: pytest.MonkeyPatch):
    """The SDK falls back to INNGEST_* env vars; keep the shell's out."""
    for key in ("INNGEST_DEV", "INNGEST_SIGNING_KEY", "INNGEST_EVENT_KEY", "INNGEST_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def firestore(monkeypatch: pytest.MonkeyPatch):
    """Point the functions at a fake Firestore and Firebase Auth."""

    def install(*users: MagicMock, auth_uids: set[str] | None = None) -> MagicMock:
        db = _db(*users)
        monkeypatch.setattr(fns, "get_db", lambda: db)
        uids = {u.id for u in users} if auth_uids is None else auth_uids
        monkeypatch.setattr(fns, "_get_auth_uids", lambda: set(uids))
        return db

    return install


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


def test_citation_sweep_sends_one_event_per_user(firestore, monkeypatch):
    firestore(_user("b"), _user("a"), _user("c"))
    monkeypatch.setattr(fns, "_pacific_date", lambda: "2026-11-06")
    client = _RecordingClient()

    res = mocked.trigger(fns.nightly_citation_sweep, _cron_event(), client)

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"day": "2026-11-06", "users_queued": 3}
    assert [(e.name, e.id, e.data) for e in client.sent] == [
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-a", {"uid": "a"}),
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-b", {"uid": "b"}),
        (fns.CITATION_CHECK_EVENT, "citation-check-2026-11-06-c", {"uid": "c"}),
    ]


def test_citation_sweep_skips_orphaned_users(firestore):
    firestore(_user("a"), _user("orphan"), _user("b"), auth_uids={"a", "b"})
    client = _RecordingClient()

    mocked.trigger(fns.nightly_citation_sweep, _cron_event(), client)

    assert [e.data["uid"] for e in client.sent] == ["a", "b"]


def test_citation_sweep_sends_large_lists_in_chunks(firestore, monkeypatch):
    monkeypatch.setattr(fns, "FAN_OUT_CHUNK", 2)
    firestore(*[_user(f"u{i}") for i in range(5)])
    client = _RecordingClient()
    sends = []
    original = client.send

    async def counting_send(events, *, skip_middleware=False):
        sends.append(len(events))
        return await original(events, skip_middleware=skip_middleware)

    client.send = counting_send

    res = mocked.trigger(fns.nightly_citation_sweep, _cron_event(), client)

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


def test_user_check_calls_run_job_for_user(firestore, monkeypatch):
    db = firestore(_user("a", notification_email="a@example.com"))
    run = AsyncMock(return_value=(4, 2))
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_processed": 4, "new_notifications": 2}
    run.assert_awaited_once()
    kwargs = run.await_args.kwargs
    assert kwargs["uid"] == "a"
    assert kwargs["user_data"] == {"notification_email": "a@example.com"}
    assert kwargs["db"] is db
    assert kwargs["dry_run"] is False


def test_user_check_passes_dry_run_through(firestore, monkeypatch):
    firestore(_user("a"))
    run = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr(fns, "run_job_for_user", run)

    mocked.trigger(
        fns.citation_check_user,
        _user_event(fns.CITATION_CHECK_EVENT, "a", dry_run=True),
        _RecordingClient(),
    )

    assert run.await_args.kwargs["dry_run"] is True


def test_user_check_skips_a_deleted_user(firestore, monkeypatch):
    firestore()
    run = AsyncMock()
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "gone"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output["skipped"]
    run.assert_not_awaited()


def test_user_check_is_retried_on_failure(firestore, monkeypatch):
    firestore(_user("a"))
    run = AsyncMock(side_effect=[RuntimeError("Firestore timeout"), (3, 1)])
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output["new_notifications"] == 1
    assert run.await_count == 2


def test_user_check_fails_after_its_retries(firestore, monkeypatch):
    firestore(_user("a"))
    run = AsyncMock(side_effect=RuntimeError("down"))
    monkeypatch.setattr(fns, "run_job_for_user", run)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.FAILED
    assert run.await_count == fns.USER_RETRIES + 1


def test_user_check_runs_off_the_event_loop_thread(firestore, monkeypatch):
    """Firestore calls block, so the check runs on a worker thread."""
    firestore(_user("a"))
    threads: list[int] = []

    async def fake_run(**kwargs):
        threads.append(threading.get_ident())
        return 0, 0

    monkeypatch.setattr(fns, "run_job_for_user", fake_run)

    mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert threads and threads[0] != threading.get_ident()


def test_a_long_user_check_continues_in_more_parts(firestore, monkeypatch):
    """Each part is one request; a user who outlasts it carries on in the
    next part, skipping papers checked since the run started."""
    firestore(_user("a"))
    calls: list[dict] = []

    async def fake_run(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            kwargs["stats"]["incomplete"] = 1
        return 5, 1

    monkeypatch.setattr(fns, "run_job_for_user", fake_run)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_processed": 15, "new_notifications": 3}
    assert len(calls) == 3
    since = {c["checked_since"] for c in calls}
    assert len(since) == 1 and None not in since  # one run start, shared by every part
    assert all(c["deadline"] is not None for c in calls)


def test_a_user_check_gives_up_after_its_part_limit(firestore, monkeypatch):
    firestore(_user("a"))

    async def never_done(**kwargs):
        kwargs["stats"]["incomplete"] = 1
        return 1, 0

    monkeypatch.setattr(fns, "run_job_for_user", never_done)

    res = mocked.trigger(
        fns.citation_check_user, _user_event(fns.CITATION_CHECK_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output["unfinished"] is True
    assert res.output["works_processed"] == fns.MAX_PARTS


def test_a_dry_run_user_check_is_one_part(firestore, monkeypatch):
    firestore(_user("a"))
    run = AsyncMock(return_value=(1, 0))

    async def incomplete(**kwargs):
        kwargs["stats"]["incomplete"] = 1
        return await run(**kwargs)

    monkeypatch.setattr(fns, "run_job_for_user", incomplete)

    mocked.trigger(
        fns.citation_check_user,
        _user_event(fns.CITATION_CHECK_EVENT, "a", dry_run=True),
        _RecordingClient(),
    )

    assert run.await_count == 1


# ---------------------------------------------------------------------------
# Weekly publication sync
# ---------------------------------------------------------------------------


def test_publication_sweep_only_queues_users_with_a_linked_author(firestore, monkeypatch):
    firestore(
        _user("a", linked_author_id="A123"),
        _user("b"),
        _user("c", linked_author_id=""),
        _user("d", linked_author_id="S2:999"),
        _user("e", linked_author_id="A456"),
        _user("orphan", linked_author_id="A789"),
        auth_uids={"a", "b", "c", "d", "e"},
    )
    monkeypatch.setattr(fns, "_pacific_date", lambda: "2026-11-08")
    client = _RecordingClient()

    res = mocked.trigger(fns.weekly_publication_sweep, _cron_event(), client)

    assert res.output == {"day": "2026-11-08", "users_queued": 2}
    assert [(e.name, e.id, e.data) for e in client.sent] == [
        (fns.PUBLICATION_SYNC_EVENT, "publication-sync-2026-11-08-a", {"uid": "a"}),
        (fns.PUBLICATION_SYNC_EVENT, "publication-sync-2026-11-08-e", {"uid": "e"}),
    ]


def test_user_sync_calls_sync_new_publications_for_user(firestore, monkeypatch):
    db = firestore(_user("a", linked_author_id="A123"))
    sync = AsyncMock(return_value=3)
    monkeypatch.setattr(fns, "sync_new_publications_for_user", sync)

    res = mocked.trigger(
        fns.publication_sync_user, _user_event(fns.PUBLICATION_SYNC_EVENT, "a"), _RecordingClient()
    )

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"uid": "a", "works_added": 3}
    kwargs = sync.await_args.kwargs
    assert kwargs["uid"] == "a"
    assert kwargs["user_data"] == {"linked_author_id": "A123"}
    assert kwargs["db"] is db
    assert kwargs["dry_run"] is False


def test_user_sync_skips_a_user_who_unlinked_since_the_sweep(firestore, monkeypatch):
    firestore(_user("a"))
    sync = AsyncMock()
    monkeypatch.setattr(fns, "sync_new_publications_for_user", sync)

    res = mocked.trigger(
        fns.publication_sync_user, _user_event(fns.PUBLICATION_SYNC_EVENT, "a"), _RecordingClient()
    )

    assert res.output["skipped"]
    sync.assert_not_awaited()


# ---------------------------------------------------------------------------
# Notification cleanup
# ---------------------------------------------------------------------------


def test_cleanup_deletes_old_notifications(firestore, monkeypatch):
    db = firestore()
    cleanup = AsyncMock(return_value={"users_processed": 2, "notifications_deleted": 5})
    monkeypatch.setattr(fns, "cleanup_old_notifications", cleanup)

    res = mocked.trigger(fns.notification_cleanup, _cron_event(), _RecordingClient())

    assert res.status is mocked.Status.COMPLETED
    assert res.output == {"users_processed": 2, "notifications_deleted": 5}
    cleanup.assert_awaited_once_with(db=db, dry_run=False)


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

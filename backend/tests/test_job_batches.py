"""The all-users jobs run in time-boxed batches that resume from a cursor,
so each request ends inside a host's time limit (300 s on Vercel Hobby)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services import citation_service, publication_sync
from app.store import UserStore
from tests.conftest import needs_db


class _Clock:
    """A monotonic clock the tests move by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


class _AllUids(set):
    def __contains__(self, item: object) -> bool:
        return True


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(citation_service, "time", c)
    monkeypatch.setattr(publication_sync, "time", c)
    monkeypatch.setattr(citation_service, "_get_auth_uids", AsyncMock(return_value=_AllUids()))
    return c


async def _users(session, *uids: str) -> None:
    """Committed users, each linked to an author, as a sweep finds them."""
    for uid in uids:
        await UserStore(session).create(uid, linked_author_id=f"A-{uid}")
    await session.commit()


def _citation_job(clock: _Clock, seconds_per_user: float, seen: list[str]):
    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += seconds_per_user
        return 1, 0

    return fake


async def _sweep(session, **kwargs):
    return await citation_service.run_job_for_all_users(
        session=session, email_service=MagicMock(), settings=MagicMock(), **kwargs
    )


@needs_db
async def test_without_a_budget_one_call_covers_everyone(clock: _Clock, pg_session) -> None:
    """With no time budget, one call checks every user, in uid order."""
    await _users(pg_session, "c", "a", "b")
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 500, seen)):
        summary = await _sweep(pg_session)
    assert seen == ["a", "b", "c"]
    assert summary["next_cursor"] is None


@needs_db
async def test_budget_stops_starting_users_and_resumes_from_cursor(clock: _Clock, pg_session) -> None:
    """Once the budget is used no new user starts, and the next call resumes after the cursor."""
    await _users(pg_session, "u1", "u2", "u3", "u4", "u5")
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 90, seen)):
        first = await _sweep(pg_session, time_budget_seconds=200)
        # u1 ends at 90 s, u2 at 180 s, u3 starts under budget and ends at 270 s.
        assert seen == ["u1", "u2", "u3"]
        assert first["next_cursor"] == "u3"
        assert first["users_processed"] == 3

        second = await _sweep(pg_session, cursor=first["next_cursor"], time_budget_seconds=200)
    assert seen == ["u1", "u2", "u3", "u4", "u5"]
    assert second["next_cursor"] is None
    assert second["users_processed"] == 2


@needs_db
async def test_a_slow_first_user_still_makes_progress(clock: _Clock, pg_session) -> None:
    """A user longer than the whole budget still finishes, so batches always advance."""
    await _users(pg_session, "a", "b")
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 999, seen)):
        summary = await _sweep(pg_session, time_budget_seconds=10)
    assert seen == ["a"]
    assert summary["next_cursor"] == "a"


@needs_db
async def test_cursor_advances_past_skipped_orphans(clock: _Clock, pg_session, monkeypatch) -> None:
    """Users with no sign-in account are skipped but still move the cursor on."""
    monkeypatch.setattr(citation_service, "_get_auth_uids", AsyncMock(return_value={"b"}))
    await _users(pg_session, "a", "b", "c")
    seen: list[str] = []

    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += 50
        return 0, 0

    with patch.object(citation_service, "run_job_for_user", new=fake):
        summary = await _sweep(pg_session, time_budget_seconds=40)
    assert seen == ["b"]
    assert summary["next_cursor"] == "b"


@needs_db
async def test_publication_sync_batches_the_same_way(clock: _Clock, pg_session) -> None:
    """The publication sync stops on its budget and resumes from its cursor too."""
    await _users(pg_session, "x", "y", "z")
    seen: list[str] = []

    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += 150
        return 1

    with patch.object(publication_sync, "sync_new_publications_for_user", new=fake):
        first = await publication_sync.sync_new_publications_for_all_users(
            session=pg_session, email_service=MagicMock(), dry_run=True, settings=MagicMock(),
            time_budget_seconds=200,
        )
        second = await publication_sync.sync_new_publications_for_all_users(
            session=pg_session, email_service=MagicMock(), dry_run=True, settings=MagicMock(),
            cursor=first["next_cursor"], time_budget_seconds=200,
        )
    assert first == {"users_processed": 2, "works_added": 2, "next_cursor": "y"}
    assert second == {"users_processed": 1, "works_added": 1, "next_cursor": None}
    assert seen == ["x", "y", "z"]


def test_run_endpoint_passes_the_batch_through() -> None:
    """The cron /jobs/run hands its cursor and budget, and the request's
    session, to the sweep and returns the sweep's next cursor."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.core.db import get_session
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        cron_secret="s3cret", app_url="https://www.citey.email"
    )
    session = MagicMock()
    app.dependency_overrides[get_session] = lambda: session
    job = AsyncMock(return_value={
        "users_processed": 1, "works_processed": 2, "new_notifications": 0, "next_cursor": "u9",
    })
    with patch("app.services.citation_service.run_job_for_all_users", new=job):
        resp = TestClient(app).post(
            "/api/jobs/run",
            json={"dry_run": True, "cursor": "u4", "time_budget_seconds": 200},
            headers={"X-Cron-Secret": "s3cret"},
        )
    assert resp.status_code == 200
    assert resp.json()["next_cursor"] == "u9"
    assert job.await_args.kwargs["cursor"] == "u4"
    assert job.await_args.kwargs["time_budget_seconds"] == 200
    assert job.await_args.kwargs["session"] is session


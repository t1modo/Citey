"""The all-users jobs run in time-boxed batches that resume from a cursor,
so each request ends inside a host's time limit (300 s on Vercel Hobby)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services import citation_service, publication_sync


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
    monkeypatch.setattr(citation_service, "_get_auth_uids", lambda: _AllUids())
    return c


def _db(*uids: str) -> MagicMock:
    docs = []
    for uid in uids:
        d = MagicMock()
        d.id = uid
        d.to_dict.return_value = {"linked_author_id": f"A-{uid}"}
        docs.append(d)
    db = MagicMock()
    db.collection.return_value.stream.return_value = docs
    return db


def _citation_job(clock: _Clock, seconds_per_user: float, seen: list[str]):
    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += seconds_per_user
        return 1, 0

    return fake


async def _sweep(db, **kwargs):
    return await citation_service.run_job_for_all_users(
        db=db, email_service=MagicMock(), settings=MagicMock(), **kwargs
    )


async def test_without_a_budget_one_call_covers_everyone(clock: _Clock) -> None:
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 500, seen)):
        summary = await _sweep(_db("c", "a", "b"))
    assert seen == ["a", "b", "c"]
    assert summary["next_cursor"] is None


async def test_budget_stops_starting_users_and_resumes_from_cursor(clock: _Clock) -> None:
    db = _db("u1", "u2", "u3", "u4", "u5")
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 90, seen)):
        first = await _sweep(db, time_budget_seconds=200)
        # u1 ends at 90 s, u2 at 180 s, u3 starts under budget and ends at 270 s.
        assert seen == ["u1", "u2", "u3"]
        assert first["next_cursor"] == "u3"
        assert first["users_processed"] == 3

        second = await _sweep(db, cursor=first["next_cursor"], time_budget_seconds=200)
    assert seen == ["u1", "u2", "u3", "u4", "u5"]
    assert second["next_cursor"] is None
    assert second["users_processed"] == 2


async def test_a_slow_first_user_still_makes_progress(clock: _Clock) -> None:
    seen: list[str] = []
    with patch.object(citation_service, "run_job_for_user", new=_citation_job(clock, 999, seen)):
        summary = await _sweep(_db("a", "b"), time_budget_seconds=10)
    assert seen == ["a"]
    assert summary["next_cursor"] == "a"


async def test_cursor_advances_past_skipped_orphans(clock: _Clock, monkeypatch) -> None:
    monkeypatch.setattr(citation_service, "_get_auth_uids", lambda: {"b"})
    seen: list[str] = []

    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += 50
        return 0, 0

    with patch.object(citation_service, "run_job_for_user", new=fake):
        summary = await _sweep(_db("a", "b", "c"), time_budget_seconds=40)
    assert seen == ["b"]
    assert summary["next_cursor"] == "b"


async def test_publication_sync_batches_the_same_way(clock: _Clock) -> None:
    db = _db("x", "y", "z")
    seen: list[str] = []

    async def fake(uid, **kwargs):
        seen.append(uid)
        clock.now += 150
        return 1

    with patch.object(publication_sync, "sync_new_publications_for_user", new=fake):
        first = await publication_sync.sync_new_publications_for_all_users(
            db=db, email_service=MagicMock(), dry_run=True, settings=MagicMock(),
            time_budget_seconds=200,
        )
        second = await publication_sync.sync_new_publications_for_all_users(
            db=db, email_service=MagicMock(), dry_run=True, settings=MagicMock(),
            cursor=first["next_cursor"], time_budget_seconds=200,
        )
    assert first == {"users_processed": 2, "works_added": 2, "next_cursor": "y"}
    assert second == {"users_processed": 1, "works_added": 1, "next_cursor": None}
    assert seen == ["x", "y", "z"]


def test_run_endpoint_passes_the_batch_through() -> None:
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        cron_secret="s3cret", app_url="https://www.citey.email"
    )
    job = AsyncMock(return_value={
        "users_processed": 1, "works_processed": 2, "new_notifications": 0, "next_cursor": "u9",
    })
    with patch("app.firebase_client.get_db"), patch(
        "app.services.citation_service.run_job_for_all_users", new=job
    ):
        resp = TestClient(app).post(
            "/jobs/run",
            json={"dry_run": True, "cursor": "u4", "time_budget_seconds": 200},
            headers={"X-Cron-Secret": "s3cret"},
        )
    assert resp.status_code == 200
    assert resp.json()["next_cursor"] == "u9"
    assert job.await_args.kwargs["cursor"] == "u4"
    assert job.await_args.kwargs["time_budget_seconds"] == 200


def test_scheduler_defaults_off_on_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISABLE_SCHEDULER", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert Settings(_env_file=None).disable_scheduler is True
    monkeypatch.setenv("DISABLE_SCHEDULER", "false")
    assert Settings(_env_file=None).disable_scheduler is False
    monkeypatch.delenv("VERCEL")
    monkeypatch.delenv("DISABLE_SCHEDULER")
    assert Settings(_env_file=None).disable_scheduler is False

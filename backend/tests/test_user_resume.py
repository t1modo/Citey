"""A user whose papers outlast one batch resumes in the next batch.

Run with TEST_DATABASE_URL set (see tests/conftest.py); skipped otherwise.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import citation_service, tracking_service
from app.services.citation_service import _CITATION_WINDOW_VERSION, run_job_for_user
from app.store import UserStore, WorkStore
from tests.conftest import needs_db

pytestmark = needs_db

_NOW = datetime.now(tz=timezone.utc)
KEY = "10.1000__mine"


def _day(days_ago: int) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _oa(title: str, *, doi: str, pub: str, wid: str) -> dict:
    return {
        "id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}",
        "title": title, "publication_year": int(pub[:4]), "publication_date": pub,
        "authorships": [], "locations": [], "type": "article",
    }


async def _seed_user_with_a_paper(session) -> int:
    """u1 tracks one paper, last checked yesterday under the current window
    (so a new citation is news, not baseline). Returns the paper's row ID."""
    await UserStore(session).create("u1", email="r@example.com")
    work, _ = await tracking_service.track_paper(
        session, "u1", KEY, {"doi": "10.1000/mine", "openalex_id": "W1", "title": "My paper"},
        now=_NOW - timedelta(days=30),
    )
    await WorkStore(session).update_fields(
        work.id, last_checked_at=_NOW - timedelta(days=1), citation_window=_CITATION_WINDOW_VERSION
    )
    await session.commit()
    return work.id


async def _run(session, email_service, **kw) -> tuple[int, int]:
    oa = [_oa("A brand new citing paper with enough words", doi="10.1/n", pub=_day(1), wid="W2")]
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.openalex_svc.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("app.services.semantic_scholar.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("app.services.citation_service.firebase_auth.get_user") as get_user:
        get_user.return_value.email_verified = True
        return await run_job_for_user("u1", session, email_service, **kw)


class _Mail:
    def __init__(self) -> None:
        self.send_digest_email = AsyncMock()


async def test_out_of_time_stops_before_the_next_paper_and_holds_the_email(pg_session) -> None:
    await _seed_user_with_a_paper(pg_session)
    mail, stats = _Mail(), {}
    works, new = await _run(pg_session, mail, stats=stats, deadline=time.monotonic() - 1)
    assert (works, new) == (0, 0)
    assert stats["incomplete"] == 1
    mail.send_digest_email.assert_not_awaited()


async def test_resumed_check_skips_papers_checked_this_run(pg_session) -> None:
    work_id = await _seed_user_with_a_paper(pg_session)
    mail, stats = _Mail(), {}
    run_start = _NOW - timedelta(minutes=5)
    await _run(pg_session, mail, stats=stats, deadline=time.monotonic() + 60, checked_since=run_start)
    assert stats["incomplete"] == 0
    mail.send_digest_email.assert_awaited_once()
    work = await WorkStore(pg_session).get(work_id)
    assert (await WorkStore(pg_session).refresh(work)).last_checked_at >= run_start

    works, _ = await _run(pg_session, _Mail(), stats={}, checked_since=run_start)
    assert works == 0


async def _users(session, *uids: str) -> None:
    for uid in uids:
        await UserStore(session).create(uid, email=f"{uid}@example.com")
    await session.commit()


class _AllUids(set):
    def __contains__(self, item: object) -> bool:
        return True


async def _sweep(session, fake, **kw):
    with patch.object(citation_service, "run_job_for_user", new=fake), \
         patch.object(citation_service, "_get_auth_uids", new=AsyncMock(return_value=_AllUids())):
        return await citation_service.run_job_for_all_users(
            session=session, email_service=MagicMock(), settings=MagicMock(), **kw
        )


async def test_a_user_who_runs_out_of_time_is_the_next_batch_s_first(pg_session) -> None:
    await _users(pg_session, "u1", "u2", "u3")
    calls: list[tuple[str, object]] = []

    async def fake(uid, stats, deadline, checked_since, **kwargs):
        calls.append((uid, checked_since))
        if uid == "u2":
            stats["incomplete"] = 1
        stats["openalex_failures"] = stats.get("openalex_failures", 0) + 1
        return 2, 0

    since = _NOW - timedelta(minutes=1)
    summary = await _sweep(pg_session, fake, time_budget_seconds=200, checked_since=since)
    assert [c[0] for c in calls] == ["u1", "u2"]
    assert all(c[1] == since for c in calls)
    assert summary["next_cursor"] == "u1"
    assert summary["openalex_failures"] == 2
    assert "incomplete" not in summary


async def test_first_user_out_of_time_resumes_from_the_start(pg_session) -> None:
    await _users(pg_session, "u1", "u2")

    async def fake(uid, stats, **kwargs):
        stats["incomplete"] = 1
        return 1, 0

    summary = await _sweep(pg_session, fake, time_budget_seconds=200,
                           checked_since=_NOW - timedelta(minutes=1))
    # Empty string, not None: None would tell the scheduler everyone is done.
    assert summary["next_cursor"] == ""


async def test_budget_reaches_inside_the_user(pg_session) -> None:
    await _users(pg_session, "u1")
    seen: dict = {}

    async def fake(uid, deadline, **kwargs):
        seen["deadline"] = deadline
        return 1, 0

    before = time.monotonic()
    await _sweep(pg_session, fake, time_budget_seconds=200)
    assert before + 199 < seen["deadline"] < time.monotonic() + 201

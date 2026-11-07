"""A user whose papers outlast one batch resumes in the next batch."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from citey.services import citation_service
from citey.services.citation_service import run_job_for_user
from tests.test_citation_accuracy import WORK_PATH, _NOW, _day, _oa, _user_db


async def _run(db, email_service, **kw) -> tuple[int, int]:
    oa = [_oa("A brand new citing paper with enough words", doi="10.1/n", pub=_day(1), wid="W2")]
    with patch("citey.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("citey.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("citey.services.citation_service.openalex_svc.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("citey.services.semantic_scholar.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("citey.services.citation_service.firebase_auth.get_user") as get_user:
        get_user.return_value.email_verified = True
        return await run_job_for_user("u1", db.store["users/u1"], db, email_service, **kw)


class _Mail:
    def __init__(self) -> None:
        self.send_digest_email = AsyncMock()


async def test_out_of_time_stops_before_the_next_paper_and_holds_the_email() -> None:
    db, mail, stats = _user_db(), _Mail(), {}
    works, new = await _run(db, mail, stats=stats, deadline=time.monotonic() - 1)
    assert (works, new) == (0, 0)
    assert stats["incomplete"] == 1
    mail.send_digest_email.assert_not_awaited()


async def test_resumed_check_skips_papers_checked_this_run() -> None:
    db, mail, stats = _user_db(), _Mail(), {}
    run_start = _NOW - timedelta(minutes=5)
    await _run(db, mail, stats=stats, deadline=time.monotonic() + 60, checked_since=run_start)
    assert stats["incomplete"] == 0
    mail.send_digest_email.assert_awaited_once()
    assert db.store[WORK_PATH]["last_checked_at"] >= run_start

    works, _ = await _run(db, _Mail(), stats={}, checked_since=run_start)
    assert works == 0


def _users(*uids: str) -> MagicMock:
    docs = []
    for uid in uids:
        d = MagicMock()
        d.id = uid
        d.to_dict.return_value = {}
        docs.append(d)
    db = MagicMock()
    db.collection.return_value.stream.return_value = docs
    return db


class _AllUids(set):
    def __contains__(self, item: object) -> bool:
        return True


async def _sweep(db, fake, **kw):
    with patch.object(citation_service, "run_job_for_user", new=fake), \
         patch.object(citation_service, "_get_auth_uids", lambda: _AllUids()):
        return await citation_service.run_job_for_all_users(
            db=db, email_service=MagicMock(), settings=MagicMock(), **kw
        )


async def test_a_user_who_runs_out_of_time_is_the_next_batch_s_first() -> None:
    calls: list[tuple[str, object]] = []

    async def fake(uid, stats, deadline, checked_since, **kwargs):
        calls.append((uid, checked_since))
        if uid == "u2":
            stats["incomplete"] = 1
        stats["openalex_failures"] = stats.get("openalex_failures", 0) + 1
        return 2, 0

    since = _NOW - timedelta(minutes=1)
    summary = await _sweep(_users("u1", "u2", "u3"), fake, time_budget_seconds=200, checked_since=since)
    assert [c[0] for c in calls] == ["u1", "u2"]
    assert all(c[1] == since for c in calls)
    assert summary["next_cursor"] == "u1"
    assert summary["openalex_failures"] == 2
    assert "incomplete" not in summary


async def test_first_user_out_of_time_resumes_from_the_start() -> None:
    async def fake(uid, stats, **kwargs):
        stats["incomplete"] = 1
        return 1, 0

    summary = await _sweep(_users("u1", "u2"), fake, time_budget_seconds=200,
                           checked_since=_NOW - timedelta(minutes=1))
    # Empty string, not None: None would tell the scheduler everyone is done.
    assert summary["next_cursor"] == ""


async def test_budget_reaches_inside_the_user() -> None:
    seen: dict = {}

    async def fake(uid, deadline, **kwargs):
        seen["deadline"] = deadline
        return 1, 0

    before = time.monotonic()
    await _sweep(_users("u1"), fake, time_budget_seconds=200)
    assert before + 199 < seen["deadline"] < time.monotonic() + 201

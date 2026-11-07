"""
The Postgres data layer (app.store), against a real database.

Run with TEST_DATABASE_URL set (see tests/conftest.py); skipped otherwise.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.models import Alert, Citation, CitingWork, User, Work
from app.store import alerts, citations, limits, users, works
from tests.conftest import needs_db

pytestmark = needs_db

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
PAPER = {"doi": "10.1/attention", "title": "Attention Is All You Need", "authors": ["A. Vaswani"], "year": 2017}


async def _user(s, uid: str = "ada") -> User:
    return await users.create(s, uid, email=f"{uid}@uni.edu")


async def _cite(s, work: Work, doi: str, *, published: str, found_at: datetime = NOW) -> int:
    cid, _ = await citations.record(
        s, work.id, doi, {f"doi:{doi}"},
        {"doi": doi, "title": f"Paper {doi}", "publication_date": published, "authors": ["B. Liskov"]},
        found_at=found_at,
    )
    return cid


# --- users --------------------------------------------------------------------


async def test_creating_a_user_twice_keeps_the_first(pg_session) -> None:
    await users.create(pg_session, "ada", email="ada@uni.edu", display_name="Ada")
    again = await users.create(pg_session, "ada", email="other@x.org")
    assert again.email == "ada@uni.edu" and again.display_name == "Ada"
    assert again.notification_email == "ada@uni.edu"


async def test_user_data_keeps_the_names_the_app_reads(pg_session) -> None:
    user = await _user(pg_session)
    await users.dismiss_work(pg_session, "ada", "10.1__X")
    await pg_session.refresh(user)
    data = users.as_user_data(user)
    assert data["dismissed_work_ids"] == ["10.1__x"]
    assert data["notify_enabled"] is True and data["last_publication_sync"] is None


async def test_dismissing_twice_records_it_once_and_tracking_clears_it(pg_session) -> None:
    await _user(pg_session)
    await users.dismiss_work(pg_session, "ada", "10.1__x")
    await users.dismiss_work(pg_session, "ada", "10.1__x")
    assert (await users.get(pg_session, "ada")).dismissed_work_keys == ["10.1__x"]
    await works.track(pg_session, "ada", "10.1__x", {"title": "X"}, now=NOW)
    await pg_session.refresh(await users.get(pg_session, "ada"))
    assert (await users.get(pg_session, "ada")).dismissed_work_keys == []


async def test_user_ids_come_in_order_after_a_cursor(pg_session) -> None:
    for uid in ("c", "a", "b"):
        await _user(pg_session, uid)
    assert await users.ids_after(pg_session) == ["a", "b", "c"]
    assert await users.ids_after(pg_session, "a") == ["b", "c"]


# --- works --------------------------------------------------------------------


async def test_a_paper_tracked_by_two_people_is_one_row(pg_session) -> None:
    await _user(pg_session, "ada")
    await _user(pg_session, "grace")
    w1, new1 = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    w2, new2 = await works.track(pg_session, "grace", "10.1__attention", {**PAPER, "title": "Other"}, now=NOW)
    assert w1.id == w2.id and new1 and new2
    assert w2.title == "Attention Is All You Need"  # the first add's metadata stays
    _, again = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    assert again is False
    assert len((await pg_session.exec(select(Work))).all()) == 1


async def test_a_later_add_fills_in_missing_metadata(pg_session) -> None:
    await _user(pg_session)
    await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    work = await works.upsert(pg_session, "10.1__attention", {**PAPER, "openalex_id": "W1", "venue": "NeurIPS"})
    assert work.openalex_id == "W1" and work.venue == "NeurIPS"


async def test_starting_to_track_announces_only_recent_citations(pg_session) -> None:
    await _user(pg_session, "ada")
    await _user(pg_session, "grace")
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    await _cite(pg_session, work, "10.9/recent", published=(NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    await _cite(pg_session, work, "10.9/old", published="2020-01-01")

    await works.track(pg_session, "grace", "10.1__attention", PAPER, now=NOW)
    got = await alerts.for_user(pg_session, "grace")
    assert [n.citing_work_doi for n in got] == ["10.9/recent"]


async def test_untracking_removes_only_that_users_alerts_and_dismisses_it(pg_session) -> None:
    await _user(pg_session, "ada")
    await _user(pg_session, "grace")
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    await works.track(pg_session, "grace", "10.1__attention", PAPER, now=NOW)
    cid = await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    await citations.alert_trackers(pg_session, cid, created_at=NOW)

    assert await works.untrack(pg_session, "ada", "10.1__attention") == 1
    assert await works.untrack(pg_session, "ada", "10.1__attention") is None
    assert await works.tracked_keys(pg_session, "ada") == set()
    assert len(await alerts.for_user(pg_session, "grace")) == 1
    assert (await users.get(pg_session, "ada")).dismissed_work_keys == ["10.1__attention"]


# --- citations ----------------------------------------------------------------


async def test_the_same_citing_paper_from_two_sources_is_one_row(pg_session) -> None:
    await _user(pg_session)
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    first, new1 = await citations.record(
        pg_session, work.id, "10.9/a", {"doi:10.9/a"}, {"doi": "10.9/a", "title": "A"}, found_at=NOW)
    # Semantic Scholar knows it by the DOI and its own ID.
    again, new2 = await citations.record(
        pg_session, work.id, "s2:123", {"doi:10.9/a", "id:s2:123"}, {"title": "A (S2)"}, found_at=NOW)
    assert first == again and new1 and not new2
    assert len((await pg_session.exec(select(CitingWork))).all()) == 1
    assert await citations.known_keys(pg_session, work.id) == {"doi:10.9/a", "id:s2:123"}


async def test_known_keys_include_those_reported_before_postgres(pg_session) -> None:
    await _user(pg_session)
    work = await works.upsert(pg_session, "10.1__attention", {**PAPER, "known_citing_keys": ["doi:10.9/old"]})
    assert await citations.known_keys(pg_session, work.id) == {"doi:10.9/old"}


async def test_a_new_citation_alerts_every_tracker_once(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    await works.track(pg_session, "grace", "10.1__attention", PAPER, now=NOW)
    cid = await _cite(pg_session, work, "10.9/a", published="2026-11-01")

    assert sorted(await citations.alert_trackers(pg_session, cid, created_at=NOW)) == ["ada", "grace"]
    assert await citations.alert_trackers(pg_session, cid, created_at=NOW) == []
    assert len((await pg_session.exec(select(Alert))).all()) == 2


# --- alerts -------------------------------------------------------------------


async def test_alerts_list_newest_first_with_the_ids_the_site_uses(pg_session) -> None:
    await _user(pg_session)
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    old = await _cite(pg_session, work, "10.9/old", published="2026-10-01")
    new = await _cite(pg_session, work, "10.9/new", published="2026-11-01")
    await alerts.add(pg_session, "ada", old, created_at=NOW - timedelta(days=40))
    await alerts.add(pg_session, "ada", new, created_at=NOW)

    listed = await alerts.for_user(pg_session, "ada")
    assert [n.citing_work_doi for n in listed] == ["10.9/new", "10.9/old"]
    assert listed[0].cited_work_id == "10.1__attention" and listed[0].id.isdigit()
    assert len(await alerts.for_user(pg_session, "ada", since=NOW - timedelta(days=30))) == 1
    assert await alerts.counts_by_work(pg_session, "ada", NOW - timedelta(days=30)) == {"10.1__attention": (2, 1)}


async def test_seen_emailed_and_pruning(pg_session) -> None:
    await _user(pg_session)
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    a = await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    b = await _cite(pg_session, work, "10.9/b", published="2026-11-01")
    await alerts.add(pg_session, "ada", a, created_at=NOW)
    await alerts.add(pg_session, "ada", b, created_at=NOW - timedelta(days=40))

    first = (await alerts.for_user(pg_session, "ada"))[0]
    assert await alerts.mark_seen(pg_session, "ada", int(first.id))
    assert not await alerts.mark_seen(pg_session, "grace", int(first.id))
    assert await alerts.mark_all_seen(pg_session, "ada") == 1

    pending = await alerts.pending_email(pg_session, "ada", NOW - timedelta(days=7))
    assert [n.citing_work_doi for n in pending] == ["10.9/a"]
    await alerts.mark_emailed(pg_session, [int(n.id) for n in pending])
    assert await alerts.pending_email(pg_session, "ada", NOW - timedelta(days=7)) == []

    assert await alerts.prune(pg_session, NOW - timedelta(days=30), dry_run=True) == 1
    assert await alerts.prune(pg_session, NOW - timedelta(days=30)) == 1
    assert len(await alerts.for_user(pg_session, "ada")) == 1
    # The citation itself stays: it is part of the paper's record.
    assert len((await pg_session.exec(select(Citation))).all()) == 2


async def test_deleting_a_user_keeps_shared_papers(pg_session) -> None:
    await _user(pg_session)
    work, _ = await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    await alerts.add(pg_session, "ada", await _cite(pg_session, work, "10.9/a", published="2026-11-01"), created_at=NOW)
    await users.delete_user(pg_session, "ada")
    assert await users.get(pg_session, "ada") is None
    assert (await pg_session.exec(select(Alert))).all() == []
    assert (await works.get_by_key(pg_session, "10.1__attention")) is not None


async def test_clearing_the_linked_author_resets_tracking(pg_session) -> None:
    await users.create(pg_session, "ada", linked_author_id="A1", linked_author_name="Ada", name_aliases=["A. L."])
    await works.track(pg_session, "ada", "10.1__attention", PAPER, now=NOW)
    await users.clear_linked_author(pg_session, "ada")
    user = await users.get(pg_session, "ada")
    await pg_session.refresh(user)
    assert user.linked_author_id is None and user.name_aliases == []
    assert await works.tracked(pg_session, "ada") == []


# --- limits -------------------------------------------------------------------


@pytest.mark.parametrize("window", [3600])
async def test_rate_limit_counts_within_the_window_then_resets(pg_session, window) -> None:
    for _ in range(3):
        assert await limits.take(pg_session, "ip_x", 3, window, NOW)
    assert not await limits.take(pg_session, "ip_x", 3, window, NOW)
    assert await limits.take(pg_session, "ip_x", 3, window, NOW + timedelta(seconds=window))

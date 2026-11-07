"""
The stores (app.store) and the services built on them (tracking_service,
alert_service), against a real database.

Run with TEST_DATABASE_URL set (see tests/conftest.py); skipped otherwise.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models import Alert, Citation, CitingWork, User, Work
from app.services import alert_service, convert, tracking_service
from app.store import AlertStore, CitationStore, LimitStore, UserStore, WorkStore
from tests.conftest import needs_db

pytestmark = needs_db

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
PAPER = {"doi": "10.1/attention", "title": "Attention Is All You Need", "authors": ["A. Vaswani"], "year": 2017}
KEY = "10.1__attention"


async def _user(s, uid: str = "ada") -> User:
    return await UserStore(s).create(uid, email=f"{uid}@uni.edu")


async def _cite(s, work: Work, doi: str, *, published: str) -> int:
    cid, _ = await CitationStore(s).record(
        work.id, doi, {f"doi:{doi}"},
        {"doi": doi, "title": f"Paper {doi}", "publication_date": published, "authors": ["B. Liskov"]},
        found_at=NOW,
    )
    return cid


# --- UserStore ----------------------------------------------------------------


async def test_creating_a_user_twice_keeps_the_first(pg_session) -> None:
    store = UserStore(pg_session)
    await store.create("ada", email="ada@uni.edu", display_name="Ada")
    again = await store.create("ada", email="other@x.org")
    assert again.email == "ada@uni.edu" and again.display_name == "Ada"
    assert again.notification_email == "ada@uni.edu"


async def test_user_data_keeps_the_names_the_app_reads(pg_session) -> None:
    store = UserStore(pg_session)
    user = await _user(pg_session)
    await store.dismiss_work("ada", "10.1__X")
    data = convert.user_data(await store.refresh(user))
    assert data["dismissed_work_ids"] == ["10.1__x"]
    assert data["notify_enabled"] is True and data["last_publication_sync"] is None


async def test_dismissing_twice_records_it_once(pg_session) -> None:
    store = UserStore(pg_session)
    user = await _user(pg_session)
    await store.dismiss_work("ada", "10.1__x")
    await store.dismiss_work("ada", "10.1__x")
    assert (await store.refresh(user)).dismissed_work_keys == ["10.1__x"]
    await store.undismiss_work("ada", "10.1__X")
    assert (await store.refresh(user)).dismissed_work_keys == []


async def test_user_ids_come_in_order_after_a_cursor(pg_session) -> None:
    for uid in ("c", "a", "b"):
        await _user(pg_session, uid)
    assert await UserStore(pg_session).ids_after() == ["a", "b", "c"]
    assert await UserStore(pg_session).ids_after("a") == ["b", "c"]


async def test_deleting_a_user_keeps_shared_papers(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await AlertStore(pg_session).add("ada", await _cite(pg_session, work, "10.9/a", published="2026-11-01"), created_at=NOW)
    await UserStore(pg_session).delete_by_id("ada")
    assert await UserStore(pg_session).get("ada") is None
    assert (await pg_session.exec(select(Alert))).all() == []
    assert await WorkStore(pg_session).get_by_key(KEY) is not None


# --- Pruning untracked papers ---------------------------------------------------

LATER = datetime.now(timezone.utc) + timedelta(days=1)  # past every row's created_at


async def test_pruning_removes_a_deleted_users_papers_and_citing_papers(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    await UserStore(pg_session).delete_by_id("ada")

    assert await WorkStore(pg_session).prune_untracked(LATER, dry_run=True) == {"works": 1, "citing_works": 1}
    assert await WorkStore(pg_session).get_by_key(KEY) is not None  # a dry run deletes nothing

    assert await WorkStore(pg_session).prune_untracked(LATER) == {"works": 1, "citing_works": 1}
    for model in (Work, Citation, CitingWork):
        assert (await pg_session.exec(select(model))).all() == []


async def test_pruning_keeps_papers_someone_still_tracks(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await tracking_service.track_paper(pg_session, "grace", KEY, PAPER, now=NOW)
    await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    await tracking_service.untrack_paper(pg_session, "ada", KEY)

    assert await WorkStore(pg_session).prune_untracked(LATER) == {"works": 0, "citing_works": 0}
    assert await WorkStore(pg_session).get_by_key(KEY) is not None
    assert len((await pg_session.exec(select(CitingWork))).all()) == 1


async def test_pruning_keeps_a_citing_paper_shared_with_a_tracked_paper(pg_session) -> None:
    await _user(pg_session)
    gone, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    kept, _ = await tracking_service.track_paper(
        pg_session, "ada", "10.1__other", {"doi": "10.1/other", "title": "Other"}, now=NOW
    )
    await _cite(pg_session, gone, "10.9/both", published="2026-11-01")
    await _cite(pg_session, kept, "10.9/both", published="2026-11-01")
    await tracking_service.untrack_paper(pg_session, "ada", KEY)

    assert await WorkStore(pg_session).prune_untracked(LATER, dry_run=True) == {"works": 1, "citing_works": 0}
    assert await WorkStore(pg_session).prune_untracked(LATER) == {"works": 1, "citing_works": 0}
    assert len((await pg_session.exec(select(CitingWork))).all()) == 1
    assert len((await pg_session.exec(select(Citation))).all()) == 1


async def test_pruning_skips_rows_newer_than_the_cutoff(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    await UserStore(pg_session).delete_by_id("ada")

    earlier = datetime.now(timezone.utc) - timedelta(days=1)
    assert await WorkStore(pg_session).prune_untracked(earlier) == {"works": 0, "citing_works": 0}
    assert await WorkStore(pg_session).get_by_key(KEY) is not None


# --- WorkStore and tracking_service -------------------------------------------


async def test_a_paper_tracked_by_two_people_is_one_row(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    w1, new1 = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    w2, new2 = await tracking_service.track_paper(pg_session, "grace", KEY, {**PAPER, "title": "Other"}, now=NOW)
    assert w1.id == w2.id and new1 and new2
    assert w2.title == "Attention Is All You Need"  # the first add's metadata stays
    _, again = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    assert again is False
    assert len((await pg_session.exec(select(Work))).all()) == 1


async def test_a_later_add_fills_in_missing_metadata(pg_session) -> None:
    await _user(pg_session)
    await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    work = await WorkStore(pg_session).upsert(KEY, {**PAPER, "openalex_id": "W1", "venue": "NeurIPS"})
    assert work.openalex_id == "W1" and work.venue == "NeurIPS"


async def test_starting_to_track_announces_only_recent_citations(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await _cite(pg_session, work, "10.9/recent", published=(NOW - timedelta(days=5)).strftime("%Y-%m-%d"))
    await _cite(pg_session, work, "10.9/old", published="2020-01-01")

    await tracking_service.track_paper(pg_session, "grace", KEY, PAPER, now=NOW)
    got = await alert_service.notifications(pg_session, "grace")
    assert [n.citing_work_doi for n in got] == ["10.9/recent"]


async def test_tracking_a_dismissed_paper_clears_the_dismissal(pg_session) -> None:
    user = await _user(pg_session)
    await UserStore(pg_session).dismiss_work("ada", KEY)
    await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    assert (await UserStore(pg_session).refresh(user)).dismissed_work_keys == []


async def test_untracking_removes_only_that_users_alerts_and_dismisses_it(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await tracking_service.track_paper(pg_session, "grace", KEY, PAPER, now=NOW)
    cid = await _cite(pg_session, work, "10.9/a", published="2026-11-01")
    await AlertStore(pg_session).add_for_trackers(cid, created_at=NOW)

    assert await tracking_service.untrack_paper(pg_session, "ada", KEY) == 1
    assert await tracking_service.untrack_paper(pg_session, "ada", KEY) is None
    assert await WorkStore(pg_session).tracked_keys("ada") == set()
    assert len(await alert_service.notifications(pg_session, "grace")) == 1
    assert (await UserStore(pg_session).get("ada")).dismissed_work_keys == [KEY]


async def test_tracked_papers_carry_alert_counts(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    alerts = AlertStore(pg_session)
    await alerts.add("ada", await _cite(pg_session, work, "10.9/a", published="2026-10-01"), created_at=NOW - timedelta(days=40))
    await alerts.add("ada", await _cite(pg_session, work, "10.9/b", published="2026-11-01"), created_at=NOW)
    [paper] = await tracking_service.tracked_papers(pg_session, "ada", now=NOW)
    assert paper.id == KEY and paper.added_at == NOW
    assert (paper.citation_count, paper.new_citations_30d) == (2, 1)


async def test_resetting_the_linked_author_clears_tracking(pg_session) -> None:
    store = UserStore(pg_session)
    user = await store.create("ada", linked_author_id="A1", linked_author_name="Ada", name_aliases=["A. L."])
    await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await tracking_service.reset_linked_author(pg_session, "ada")
    user = await store.refresh(user)
    assert user.linked_author_id is None and user.name_aliases == []
    assert await WorkStore(pg_session).tracked("ada") == []


# --- CitationStore -------------------------------------------------------------


async def test_the_same_citing_paper_from_two_sources_is_one_row(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    store = CitationStore(pg_session)
    first, new1 = await store.record(work.id, "10.9/a", {"doi:10.9/a"}, {"doi": "10.9/a", "title": "A"}, found_at=NOW)
    # Semantic Scholar knows it by the DOI and its own ID.
    again, new2 = await store.record(work.id, "s2:123", {"doi:10.9/a", "id:s2:123"}, {"title": "A (S2)"}, found_at=NOW)
    assert first == again and new1 and not new2
    assert len((await pg_session.exec(select(CitingWork))).all()) == 1
    assert await store.known_keys(work.id) == {"doi:10.9/a", "id:s2:123"}


async def test_known_keys_include_those_reported_before_postgres(pg_session) -> None:
    work = await WorkStore(pg_session).upsert(KEY, {**PAPER, "known_citing_keys": ["doi:10.9/old"]})
    assert await CitationStore(pg_session).known_keys(work.id) == {"doi:10.9/old"}


# --- AlertStore and alert_service -------------------------------------------------


async def test_a_new_citation_alerts_every_tracker_once(pg_session) -> None:
    for uid in ("ada", "grace"):
        await _user(pg_session, uid)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    await tracking_service.track_paper(pg_session, "grace", KEY, PAPER, now=NOW)
    cid = await _cite(pg_session, work, "10.9/a", published="2026-11-01")

    store = AlertStore(pg_session)
    assert sorted(await store.add_for_trackers(cid, created_at=NOW)) == ["ada", "grace"]
    assert await store.add_for_trackers(cid, created_at=NOW) == []
    assert len((await pg_session.exec(select(Alert))).all()) == 2


async def test_alerts_list_newest_first_with_the_ids_the_site_uses(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    store = AlertStore(pg_session)
    await store.add("ada", await _cite(pg_session, work, "10.9/old", published="2026-10-01"), created_at=NOW - timedelta(days=40))
    await store.add("ada", await _cite(pg_session, work, "10.9/new", published="2026-11-01"), created_at=NOW)

    listed = await alert_service.notifications(pg_session, "ada")
    assert [n.citing_work_doi for n in listed] == ["10.9/new", "10.9/old"]
    assert listed[0].cited_work_id == KEY and listed[0].id.isdigit()
    assert len(await alert_service.notifications(pg_session, "ada", since=NOW - timedelta(days=30))) == 1
    assert (await alert_service.notification(pg_session, "ada", int(listed[0].id))).citing_work_doi == "10.9/new"
    assert await alert_service.notification(pg_session, "grace", int(listed[0].id)) is None


async def test_seen_emailed_and_pruning(pg_session) -> None:
    await _user(pg_session)
    work, _ = await tracking_service.track_paper(pg_session, "ada", KEY, PAPER, now=NOW)
    store = AlertStore(pg_session)
    await store.add("ada", await _cite(pg_session, work, "10.9/a", published="2026-11-01"), created_at=NOW)
    await store.add("ada", await _cite(pg_session, work, "10.9/b", published="2026-11-01"), created_at=NOW - timedelta(days=40))

    first = (await alert_service.notifications(pg_session, "ada"))[0]
    assert await store.mark_seen("ada", int(first.id))
    assert not await store.mark_seen("grace", int(first.id))
    assert await store.mark_all_seen("ada") == 1

    pending = await alert_service.pending_email(pg_session, "ada", NOW - timedelta(days=7))
    assert [n.citing_work_doi for n in pending] == ["10.9/a"]
    await store.mark_emailed([int(n.id) for n in pending])
    assert await alert_service.pending_email(pg_session, "ada", NOW - timedelta(days=7)) == []

    assert await store.prune(NOW - timedelta(days=30), dry_run=True) == 1
    assert await store.prune(NOW - timedelta(days=30)) == 1
    assert len(await alert_service.notifications(pg_session, "ada")) == 1
    # The citation itself stays: it is part of the paper's record.
    assert len((await pg_session.exec(select(Citation))).all()) == 2


# --- LimitStore ---------------------------------------------------------------


async def test_rate_limit_counts_within_the_window_then_resets(pg_session) -> None:
    store = LimitStore(pg_session)
    for _ in range(3):
        assert await store.take("ip_x", 3, 3600, NOW)
    assert not await store.take("ip_x", 3, 3600, NOW)
    assert await store.take("ip_x", 3, 3600, NOW + timedelta(seconds=3600))

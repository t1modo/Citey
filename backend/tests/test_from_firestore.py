"""
Copying Firestore data into Postgres (app.services.firestore_copy), with
Firestore documents as plain dicts. Needs TEST_DATABASE_URL.
"""

from datetime import datetime, timezone

from sqlmodel import select

from app.models import Alert, Citation, CitingWork, User, UserWork, Work
from app.services import alert_service
from app.services.firestore_copy import as_datetime, copy_user
from app.store import CitationStore, WorkStore
from tests.conftest import needs_db

T1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
T2 = datetime(2026, 11, 1, tzinfo=timezone.utc)

ADA = {
    "uid": "ada", "email": "ada@uni.edu", "display_name": "Ada", "notify_enabled": True,
    "notification_email": "ada@lab.org", "verified_notification_email": "ada@lab.org",
    "linked_author_id": "A1", "linked_author_name": "Ada Lovelace",
    "additional_linked_authors": [{"id": "A2", "name": "A. Lovelace"}],
    "name_aliases": ["A. L."], "dismissed_work_ids": ["10.1__OLD"],
    "last_publication_sync": T1, "created_at": "2025-01-02T03:04:05Z",
}
PAPER = {
    "doi": "10.1/attention", "openalex_id": "W123", "title": "Attention Is All You Need",
    "authors": ["A. Vaswani"], "year": 2017, "added_at": T1, "last_checked_at": T1,
    "citation_window": 4, "notified_keys": ["doi:10.9/old-one"],
}
NOTE = {
    "cited_work_id": "10.1__attention", "cited_work_title": "Attention Is All You Need",
    "citing_work_id": "10.9/new-one", "citing_work_doi": "10.9/new-one",
    "citing_work_title": "A New Paper That Cites Attention", "citing_authors": ["B. Liskov"],
    "citing_affiliations": ["MIT"], "citing_year": 2026, "citing_publication_date": "2026-10-28",
    "seen": False, "emailed": False, "created_at": T2,
}


def test_firestore_times_become_aware_datetimes() -> None:
    assert as_datetime("2025-01-02T03:04:05Z") == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert as_datetime(datetime(2025, 1, 2)) == datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert as_datetime("not a date") is None and as_datetime(None) is None


@needs_db
async def test_a_user_is_copied_with_settings_papers_and_alerts(pg_session) -> None:
    copied = await copy_user(
        pg_session, "ada", ADA, {"10.1__attention": PAPER}, {"10.1__attention__10_9__new-one": NOTE}
    )
    await pg_session.commit()
    assert (copied.users, copied.tracked, copied.alerts) == (1, 1, 1)

    user = await pg_session.get(User, "ada")
    assert user.notification_email == "ada@lab.org" and user.verified_notification_email == "ada@lab.org"
    assert user.additional_linked_authors == [{"id": "A2", "name": "A. Lovelace"}]
    assert user.dismissed_work_keys == ["10.1__old"]
    assert user.last_publication_sync_at == T1
    assert user.created_at == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    work = await WorkStore(pg_session).get_by_key("10.1__attention")
    assert work.openalex_id == "W123" and work.citation_window == 4 and work.last_checked_at == T1
    # Keys reported in Firestore, plus the copied notification's.
    known = await CitationStore(pg_session).known_keys(work.id)
    assert {"doi:10.9/old-one", "doi:10.9/new-one", "id:10.9/new-one"} <= known

    [n] = await alert_service.notifications(pg_session, "ada")
    assert n.cited_work_id == "10.1__attention" and n.citing_work_doi == "10.9/new-one"
    assert n.citing_affiliations == ["MIT"] and n.created_at == T2 and not n.seen and not n.emailed
    [(_, uw)] = await WorkStore(pg_session).tracked("ada")
    assert uw.added_at == T1


@needs_db
async def test_copying_again_changes_nothing(pg_session) -> None:
    args = ({"10.1__attention": PAPER}, {"n1": NOTE})
    await copy_user(pg_session, "ada", ADA, *args)
    again = await copy_user(pg_session, "ada", ADA, *args)
    await pg_session.commit()
    assert again.alerts == 0
    for model in (User, Work, UserWork, CitingWork, Citation, Alert):
        assert len((await pg_session.exec(select(model))).all()) == 1, model.__name__


@needs_db
async def test_two_users_tracking_one_paper_share_it(pg_session) -> None:
    grace_paper = {**PAPER, "last_checked_at": T2, "notified_keys": ["doi:10.9/graces-old"], "openalex_id": None}
    await copy_user(pg_session, "ada", ADA, {"10.1__attention": PAPER}, {"n1": NOTE})
    await copy_user(pg_session, "grace", {"email": "g@x.org"}, {"10.1__attention": grace_paper}, {"n1": NOTE})
    await pg_session.commit()

    [work] = (await pg_session.exec(select(Work))).all()
    assert work.last_checked_at == T2  # the latest check
    assert work.openalex_id == "W123"  # kept from the copy that had it
    assert {"doi:10.9/old-one", "doi:10.9/graces-old"} <= set(work.known_citing_keys)
    assert len((await pg_session.exec(select(Citation))).all()) == 1  # one citation, two alerts
    assert len((await pg_session.exec(select(Alert))).all()) == 2


@needs_db
async def test_old_notifications_without_emailed_count_as_sent(pg_session) -> None:
    note = {k: v for k, v in NOTE.items() if k != "emailed"}
    await copy_user(pg_session, "ada", ADA, {"10.1__attention": PAPER}, {"n1": note})
    [alert] = (await pg_session.exec(select(Alert))).all()
    assert alert.emailed is True


@needs_db
async def test_notifications_for_papers_no_longer_tracked_are_skipped(pg_session) -> None:
    copied = await copy_user(pg_session, "ada", ADA, {}, {"n1": NOTE})
    assert copied.alerts == 0 and "not tracked" in copied.skipped[0]
    assert (await pg_session.exec(select(Citation))).all() == []

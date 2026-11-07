"""
Tests for app.services.publication_sync.

OpenAlex and email are mocked. The sync itself runs against a real
database (TEST_DATABASE_URL, see tests/conftest.py): tests that need it are
marked ``needs_db`` and skipped without one.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import User
from app.services import convert, tracking_service
from app.services.normalize import dedupe_works_by_title, normalize_doi
from app.services.publication_sync import (
    sync_new_publications_for_all_users,
    sync_new_publications_for_user,
)
from app.store import UserStore, WorkStore
from tests.conftest import needs_db

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# normalize_doi
# ---------------------------------------------------------------------------


def test_strip_doi_https_prefix() -> None:
    assert normalize_doi("https://doi.org/10.1234/test") == "10.1234/test"


def test_strip_doi_http_prefix() -> None:
    assert normalize_doi("http://doi.org/10.1234/test") == "10.1234/test"


def test_strip_doi_bare_doi() -> None:
    assert normalize_doi("10.1234/test") == "10.1234/test"


def test_strip_doi_none_returns_none() -> None:
    assert normalize_doi(None) is None


def test_strip_doi_empty_string_returns_none() -> None:
    assert normalize_doi("") is None


def test_normalize_doi_lowercases_and_strips_dx_prefix() -> None:
    assert normalize_doi("https://dx.doi.org/10.48550/arXiv.2101.0001") == "10.48550/arxiv.2101.0001"


def test_dedupe_prefers_published_version_over_arxiv() -> None:
    works = [
        {"doi": "10.48550/arXiv.1", "title": "Deep Learning for Widgets"},
        {"doi": "10.1000/journal.1", "title": "Deep learning for widgets."},
        {"doi": "10.1000/other", "title": "Something else entirely"},
        {"doi": None, "title": "No DOI"},
    ]
    kept = {w["doi"] for w in dedupe_works_by_title(works)}
    assert kept == {"10.1000/journal.1", "10.1000/other"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    s = MagicMock()
    s.app_name = "Citey"
    s.app_url = "http://localhost:3000"
    s.support_email = "support@citey.app"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_oa_work(doi: str, title: str = "Test Paper") -> dict:
    """Return a minimal raw OpenAlex work dict."""
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "authorships": [{"author": {"display_name": "Jane Smith"}}],
        "publication_year": 2024,
        "id": "https://openalex.org/W1234567890",
        "cited_by_count": 5,
        "type": "journal-article",
        "primary_location": None,
        "primary_topic": None,
        "topics": [],
    }


def _openalex(*works: dict):
    """OpenAlex answers the author's works with *works*."""
    return patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=list(works)),
    )


def _email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_new_publications_email = AsyncMock()
    return svc


async def _user(s, uid: str = "u1", email: str = "", **fields) -> User:
    """A user linked to OpenAlex author A123 unless *fields* say otherwise."""
    fields.setdefault("linked_author_id", "A123")
    return await UserStore(s).create(uid, email=email, **fields)


async def _track(s, uid: str, doi: str) -> None:
    key = doi.replace("/", "__")
    await tracking_service.track_paper(s, uid, key, {"doi": doi, "title": doi}, now=NOW)


async def _sync(s, uid: str = "u1", *, email_service=None, dry_run: bool = False) -> int:
    """Sync *uid*, reading the user from the database as the jobs do."""
    return await sync_new_publications_for_user(
        uid=uid,
        session=s,
        email_service=email_service or _email_service(),
        dry_run=dry_run,
        settings=_make_settings(),
    )


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — skip conditions
# ---------------------------------------------------------------------------


async def test_skips_user_without_linked_author() -> None:
    """No linked author: nothing is fetched and the database is not touched."""
    session = MagicMock()
    with _openalex() as oa:
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={},
            session=session,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )
    assert result == 0
    assert session.mock_calls == []
    oa.assert_not_awaited()


async def test_skips_s2_linked_author() -> None:
    """Semantic Scholar profiles can't list every work, so they are skipped."""
    session = MagicMock()
    with _openalex() as oa:
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "S2:12345"},
            session=session,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )
    assert result == 0
    assert session.mock_calls == []
    oa.assert_not_awaited()


async def test_returns_zero_when_openalex_returns_empty() -> None:
    """An author with no works on OpenAlex adds nothing."""
    with _openalex():
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            session=MagicMock(),
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )
    assert result == 0


@needs_db
async def test_skips_works_without_doi(pg_session) -> None:
    """A work with no DOI can't be tracked, so it is left out."""
    await _user(pg_session)
    with _openalex({**_make_oa_work("10.1234/x"), "doi": None}):
        result = await _sync(pg_session)
    assert result == 0
    assert await WorkStore(pg_session).tracked_keys("u1") == set()


@needs_db
async def test_skips_works_already_tracked(pg_session) -> None:
    """A paper the user already tracks is not added again."""
    await _user(pg_session)
    await _track(pg_session, "u1", "10.1234/existing")
    with _openalex(_make_oa_work("10.1234/existing")):
        result = await _sync(pg_session)
    assert result == 0
    assert await WorkStore(pg_session).tracked_keys("u1") == {"10.1234__existing"}


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — adding works
# ---------------------------------------------------------------------------


@needs_db
async def test_adds_new_works_and_returns_count(pg_session) -> None:
    """Every new publication becomes a tracked paper, with OpenAlex's metadata."""
    await _user(pg_session)
    with _openalex(
        _make_oa_work("10.1234/paper-one", "Paper One"),
        _make_oa_work("10.1234/paper-two", "Paper Two"),
    ):
        result = await _sync(pg_session)

    assert result == 2
    works = WorkStore(pg_session)
    assert await works.tracked_keys("u1") == {"10.1234__paper-one", "10.1234__paper-two"}
    one = await works.get_by_key("10.1234__paper-one")
    assert one.title == "Paper One" and one.doi == "10.1234/paper-one"
    assert one.authors == ["Jane Smith"] and one.year == 2024


@needs_db
async def test_only_adds_works_not_already_tracked(pg_session) -> None:
    """Of an old and a new paper, only the new one is added."""
    await _user(pg_session)
    await _track(pg_session, "u1", "10.1234/old")
    with _openalex(
        _make_oa_work("10.1234/old", "Old Paper"),   # already tracked
        _make_oa_work("10.1234/new", "New Paper"),   # should be added
    ):
        result = await _sync(pg_session)

    assert result == 1
    assert await WorkStore(pg_session).tracked_keys("u1") == {"10.1234__old", "10.1234__new"}


@needs_db
async def test_records_last_publication_sync_timestamp(pg_session) -> None:
    """A sync that adds papers records when it ran on the user's row."""
    user = await _user(pg_session)
    with _openalex(_make_oa_work("10.1234/new")):
        await _sync(pg_session)

    user = await UserStore(pg_session).refresh(user)
    assert user.last_publication_sync_at is not None
    assert convert.user_data(user)["last_publication_sync"] == user.last_publication_sync_at


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — dry run
# ---------------------------------------------------------------------------


@needs_db
async def test_dry_run_returns_count_without_writing(pg_session) -> None:
    """A dry run counts the new papers but tracks nothing and records no sync."""
    user = await _user(pg_session)
    with _openalex(_make_oa_work("10.1234/dry-paper")):
        result = await _sync(pg_session, dry_run=True)

    assert result == 1
    assert await WorkStore(pg_session).tracked_keys("u1") == set()
    assert await WorkStore(pg_session).get_by_key("10.1234__dry-paper") is None
    assert (await UserStore(pg_session).refresh(user)).last_publication_sync_at is None


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — email notification
# ---------------------------------------------------------------------------


@needs_db
async def test_sends_email_when_both_flags_enabled(pg_session) -> None:
    """With both notification flags on, the user hears about the new titles."""
    await _user(
        pg_session,
        email="jane@example.com",
        display_name="Dr. Jane",
        notify_new_publications=True,
        notify_enabled=True,
    )
    email_svc = _email_service()
    with _openalex(_make_oa_work("10.1234/new", "Great Paper")):
        await _sync(pg_session, email_service=email_svc)

    email_svc.send_new_publications_email.assert_awaited_once()
    kwargs = email_svc.send_new_publications_email.call_args.kwargs
    assert kwargs["to_email"] == "jane@example.com"
    assert kwargs["recipient_name"] == "Dr. Jane"
    assert kwargs["new_titles"] == ["Great Paper"]


@needs_db
async def test_falls_back_to_account_email_when_no_notification_email(pg_session) -> None:
    """With no notification address set, the email goes to the account email."""
    user = await _user(pg_session, email="fallback@example.com")
    await UserStore(pg_session).update_fields("u1", notification_email=None)
    await UserStore(pg_session).refresh(user)
    email_svc = _email_service()
    with _openalex(_make_oa_work("10.1234/new")):
        await _sync(pg_session, email_service=email_svc)

    kwargs = email_svc.send_new_publications_email.call_args.kwargs
    assert kwargs["to_email"] == "fallback@example.com"


@needs_db
async def test_no_email_when_notify_new_publications_false(pg_session) -> None:
    """A user who turned off new-publication emails gets none."""
    await _user(pg_session, email="jane@example.com", notify_new_publications=False, notify_enabled=True)
    email_svc = _email_service()
    with _openalex(_make_oa_work("10.1234/new")):
        await _sync(pg_session, email_service=email_svc)

    email_svc.send_new_publications_email.assert_not_awaited()


@needs_db
async def test_no_email_when_global_notifications_disabled(pg_session) -> None:
    """A user who turned off all emails gets none."""
    await _user(pg_session, email="jane@example.com", notify_new_publications=True, notify_enabled=False)
    email_svc = _email_service()
    with _openalex(_make_oa_work("10.1234/new")):
        await _sync(pg_session, email_service=email_svc)

    email_svc.send_new_publications_email.assert_not_awaited()


@needs_db
async def test_no_email_when_no_address_on_profile(pg_session) -> None:
    """With no address anywhere on the profile, no email is sent."""
    await _user(pg_session)  # no email at all
    email_svc = _email_service()
    with _openalex(_make_oa_work("10.1234/new")):
        await _sync(pg_session, email_service=email_svc)

    email_svc.send_new_publications_email.assert_not_awaited()


# ---------------------------------------------------------------------------
# sync_new_publications_for_all_users
# ---------------------------------------------------------------------------


class _AllUids(set):
    """Pretends every uid has a Clerk account."""

    def __contains__(self, item: object) -> bool:  # noqa: D401
        return True


@pytest.fixture(autouse=True)
def _every_user_has_an_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """The all-users jobs look up Clerk accounts to skip orphans; stub it."""
    monkeypatch.setattr(
        "app.services.citation_service._get_auth_uids", AsyncMock(return_value=_AllUids())
    )


async def _users(s, **linked: str | None) -> None:
    """Users by uid, each linked to the given author (None: not linked),
    committed as the sweep would find them."""
    for uid, author in linked.items():
        await UserStore(s).create(uid, linked_author_id=author)
    await s.commit()


async def _sweep(s) -> dict:
    return await sync_new_publications_for_all_users(
        session=s,
        email_service=MagicMock(),
        dry_run=False,
        settings=_make_settings(),
    )


@needs_db
async def test_all_users_skips_users_without_linked_author(pg_session) -> None:
    """Only users with a linked author are synced."""
    await _users(pg_session, u_linked="A123", u_unlinked=None)

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=AsyncMock(return_value=0),
    ) as mock_per_user:
        await _sweep(pg_session)

    assert mock_per_user.call_count == 1
    assert mock_per_user.call_args.kwargs["uid"] == "u_linked"
    assert mock_per_user.call_args.kwargs["user_data"]["linked_author_id"] == "A123"


@needs_db
async def test_all_users_returns_correct_summary(pg_session) -> None:
    """The summary adds up users synced and papers added across everyone."""
    await _users(pg_session, u0="A0", u1="A1", u2="A2")

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=AsyncMock(return_value=2),  # 2 new works per user
    ):
        summary = await _sweep(pg_session)

    assert summary["users_processed"] == 3
    assert summary["works_added"] == 6


@needs_db
async def test_all_users_continues_after_per_user_failure(pg_session) -> None:
    """One user's failure doesn't stop the sweep for the rest."""
    await _users(pg_session, u1="A1", u2="A2")

    call_count = 0

    async def _flaky_sync(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("OpenAlex timeout")
        return 3

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=_flaky_sync,
    ):
        summary = await _sweep(pg_session)

    # u1 failed (exception swallowed), u2 succeeded with 3 new works
    assert summary["users_processed"] == 1
    assert summary["works_added"] == 3


@needs_db
async def test_all_users_empty_db_returns_zero_summary(pg_session) -> None:
    """With no users, the sweep reports nothing done."""
    summary = await _sweep(pg_session)

    assert summary["users_processed"] == 0
    assert summary["works_added"] == 0
    assert summary["next_cursor"] is None


@needs_db
async def test_all_users_skips_users_without_a_sign_in_account(pg_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Users with no Clerk account (orphans) are not synced."""
    monkeypatch.setattr(
        "app.services.citation_service._get_auth_uids", AsyncMock(return_value={"u_real"})
    )
    await _users(pg_session, u_real="A1", u_orphan="A2")

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=AsyncMock(return_value=0),
    ) as mock_per_user:
        await _sweep(pg_session)

    assert [c.kwargs["uid"] for c in mock_per_user.call_args_list] == ["u_real"]


@needs_db
async def test_all_users_adds_papers_end_to_end(pg_session) -> None:
    """Without stubbing the per-user sync, the sweep tracks each linked user's new papers."""
    await _users(pg_session, u1="A1", u2=None)
    with _openalex(_make_oa_work("10.1234/new", "New Paper")):
        summary = await _sweep(pg_session)

    assert summary == {"users_processed": 1, "works_added": 1, "next_cursor": None}
    assert await WorkStore(pg_session).tracked_keys("u1") == {"10.1234__new"}
    assert await WorkStore(pg_session).tracked_keys("u2") == set()

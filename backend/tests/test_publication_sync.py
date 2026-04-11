"""
Tests for app.services.publication_sync.

All Firestore I/O and OpenAlex HTTP calls are replaced with lightweight
in-process mocks — no real network or Firebase connections required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.publication_sync import (
    _strip_doi,
    sync_new_publications_for_all_users,
    sync_new_publications_for_user,
)


# ---------------------------------------------------------------------------
# _strip_doi
# ---------------------------------------------------------------------------


def test_strip_doi_https_prefix() -> None:
    assert _strip_doi("https://doi.org/10.1234/test") == "10.1234/test"


def test_strip_doi_http_prefix() -> None:
    assert _strip_doi("http://doi.org/10.1234/test") == "10.1234/test"


def test_strip_doi_bare_doi() -> None:
    assert _strip_doi("10.1234/test") == "10.1234/test"


def test_strip_doi_none_returns_none() -> None:
    assert _strip_doi(None) is None


def test_strip_doi_empty_string_returns_none() -> None:
    assert _strip_doi("") is None


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


def _make_db(existing_doc_ids: list[str] | None = None):
    """
    Build a minimal Firestore mock.

    Returns (db, works_ref, user_ref) so tests can assert on calls.
    """
    existing_doc_ids = existing_doc_ids or []
    stream_docs = [MagicMock(id=doc_id) for doc_id in existing_doc_ids]

    works_ref = MagicMock()
    works_ref.stream.return_value = stream_docs
    # works_ref.document(work_id).set(...) — all resolve to the same mock
    works_ref.document.return_value.set = MagicMock()

    user_ref = MagicMock()
    user_ref.collection.return_value = works_ref
    user_ref.set = MagicMock()

    db = MagicMock()
    db.collection.return_value.document.return_value = user_ref

    return db, works_ref, user_ref


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — skip conditions
# ---------------------------------------------------------------------------


async def test_skips_user_without_linked_author() -> None:
    db, _, _ = _make_db()
    result = await sync_new_publications_for_user(
        uid="u1",
        user_data={},
        db=db,
        email_service=MagicMock(),
        dry_run=False,
        settings=_make_settings(),
    )
    assert result == 0
    db.collection.assert_not_called()


async def test_skips_s2_linked_author() -> None:
    db, _, _ = _make_db()
    result = await sync_new_publications_for_user(
        uid="u1",
        user_data={"linked_author_id": "S2:12345"},
        db=db,
        email_service=MagicMock(),
        dry_run=False,
        settings=_make_settings(),
    )
    assert result == 0
    db.collection.assert_not_called()


async def test_returns_zero_when_openalex_returns_empty() -> None:
    db, _, _ = _make_db()
    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )
    assert result == 0


async def test_skips_works_without_doi() -> None:
    db, works_ref, _ = _make_db()
    no_doi_work = {**_make_oa_work("10.1234/x"), "doi": None}

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[no_doi_work]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert result == 0
    works_ref.document.return_value.set.assert_not_called()


async def test_skips_works_already_tracked() -> None:
    # DOI "10.1234/existing" → work_id "10.1234__existing"
    existing_id = "10.1234__existing"
    db, works_ref, _ = _make_db(existing_doc_ids=[existing_id])

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/existing")]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert result == 0
    works_ref.document.return_value.set.assert_not_called()


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — adding works
# ---------------------------------------------------------------------------


async def test_adds_new_works_and_returns_count() -> None:
    db, works_ref, _ = _make_db()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[
            _make_oa_work("10.1234/paper-one", "Paper One"),
            _make_oa_work("10.1234/paper-two", "Paper Two"),
        ]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert result == 2
    assert works_ref.document.return_value.set.call_count == 2


async def test_only_adds_works_not_already_tracked() -> None:
    existing_id = "10.1234__old"
    db, works_ref, _ = _make_db(existing_doc_ids=[existing_id])

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[
            _make_oa_work("10.1234/old", "Old Paper"),   # already tracked
            _make_oa_work("10.1234/new", "New Paper"),   # should be added
        ]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert result == 1
    assert works_ref.document.return_value.set.call_count == 1


async def test_records_last_publication_sync_timestamp() -> None:
    db, _, user_ref = _make_db()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    # The user document should receive a set() call with the sync timestamp
    user_ref.set.assert_called_once()
    call_args = user_ref.set.call_args
    assert "last_publication_sync" in call_args[0][0]


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — dry run
# ---------------------------------------------------------------------------


async def test_dry_run_returns_count_without_writing() -> None:
    db, works_ref, user_ref = _make_db()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/dry-paper")]),
    ):
        result = await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},
            db=db,
            email_service=MagicMock(),
            dry_run=True,
            settings=_make_settings(),
        )

    assert result == 1
    # Nothing written to Firestore
    works_ref.document.return_value.set.assert_not_called()
    user_ref.set.assert_not_called()


# ---------------------------------------------------------------------------
# sync_new_publications_for_user — email notification
# ---------------------------------------------------------------------------


async def test_sends_email_when_both_flags_enabled() -> None:
    db, _, _ = _make_db()
    email_svc = MagicMock()
    email_svc.send_new_publications_email = AsyncMock()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new", "Great Paper")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={
                "linked_author_id": "A123",
                "notify_new_publications": True,
                "notify_enabled": True,
                "notification_email": "jane@example.com",
                "display_name": "Dr. Jane",
            },
            db=db,
            email_service=email_svc,
            dry_run=False,
            settings=_make_settings(),
        )

    email_svc.send_new_publications_email.assert_awaited_once()
    kwargs = email_svc.send_new_publications_email.call_args.kwargs
    assert kwargs["to_email"] == "jane@example.com"
    assert kwargs["recipient_name"] == "Dr. Jane"
    assert kwargs["new_titles"] == ["Great Paper"]


async def test_falls_back_to_account_email_when_no_notification_email() -> None:
    db, _, _ = _make_db()
    email_svc = MagicMock()
    email_svc.send_new_publications_email = AsyncMock()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={
                "linked_author_id": "A123",
                "notify_new_publications": True,
                "notify_enabled": True,
                "email": "fallback@example.com",
            },
            db=db,
            email_service=email_svc,
            dry_run=False,
            settings=_make_settings(),
        )

    kwargs = email_svc.send_new_publications_email.call_args.kwargs
    assert kwargs["to_email"] == "fallback@example.com"


async def test_no_email_when_notify_new_publications_false() -> None:
    db, _, _ = _make_db()
    email_svc = MagicMock()
    email_svc.send_new_publications_email = AsyncMock()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={
                "linked_author_id": "A123",
                "notify_new_publications": False,
                "notify_enabled": True,
                "notification_email": "jane@example.com",
            },
            db=db,
            email_service=email_svc,
            dry_run=False,
            settings=_make_settings(),
        )

    email_svc.send_new_publications_email.assert_not_awaited()


async def test_no_email_when_global_notifications_disabled() -> None:
    db, _, _ = _make_db()
    email_svc = MagicMock()
    email_svc.send_new_publications_email = AsyncMock()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={
                "linked_author_id": "A123",
                "notify_new_publications": True,
                "notify_enabled": False,
                "notification_email": "jane@example.com",
            },
            db=db,
            email_service=email_svc,
            dry_run=False,
            settings=_make_settings(),
        )

    email_svc.send_new_publications_email.assert_not_awaited()


async def test_no_email_when_no_address_on_profile() -> None:
    db, _, _ = _make_db()
    email_svc = MagicMock()
    email_svc.send_new_publications_email = AsyncMock()

    with patch(
        "app.services.publication_sync.openalex_svc.get_works_by_author",
        new=AsyncMock(return_value=[_make_oa_work("10.1234/new")]),
    ):
        await sync_new_publications_for_user(
            uid="u1",
            user_data={"linked_author_id": "A123"},  # no email field at all
            db=db,
            email_service=email_svc,
            dry_run=False,
            settings=_make_settings(),
        )

    email_svc.send_new_publications_email.assert_not_awaited()


# ---------------------------------------------------------------------------
# sync_new_publications_for_all_users
# ---------------------------------------------------------------------------


async def test_all_users_skips_users_without_linked_author() -> None:
    u_linked = MagicMock()
    u_linked.id = "u_linked"
    u_linked.to_dict.return_value = {"linked_author_id": "A123"}

    u_unlinked = MagicMock()
    u_unlinked.id = "u_unlinked"
    u_unlinked.to_dict.return_value = {}

    db = MagicMock()
    db.collection.return_value.stream.return_value = [u_linked, u_unlinked]

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=AsyncMock(return_value=0),
    ) as mock_per_user:
        await sync_new_publications_for_all_users(
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert mock_per_user.call_count == 1
    assert mock_per_user.call_args.kwargs["uid"] == "u_linked"


async def test_all_users_returns_correct_summary() -> None:
    users = []
    for i in range(3):
        u = MagicMock()
        u.id = f"u{i}"
        u.to_dict.return_value = {"linked_author_id": f"A{i}"}
        users.append(u)

    db = MagicMock()
    db.collection.return_value.stream.return_value = users

    with patch(
        "app.services.publication_sync.sync_new_publications_for_user",
        new=AsyncMock(return_value=2),  # 2 new works per user
    ):
        summary = await sync_new_publications_for_all_users(
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    assert summary["users_processed"] == 3
    assert summary["works_added"] == 6


async def test_all_users_continues_after_per_user_failure() -> None:
    u1 = MagicMock()
    u1.id = "u1"
    u1.to_dict.return_value = {"linked_author_id": "A1"}

    u2 = MagicMock()
    u2.id = "u2"
    u2.to_dict.return_value = {"linked_author_id": "A2"}

    db = MagicMock()
    db.collection.return_value.stream.return_value = [u1, u2]

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
        summary = await sync_new_publications_for_all_users(
            db=db,
            email_service=MagicMock(),
            dry_run=False,
            settings=_make_settings(),
        )

    # u1 failed (exception swallowed), u2 succeeded with 3 new works
    assert summary["users_processed"] == 1
    assert summary["works_added"] == 3


async def test_all_users_empty_db_returns_zero_summary() -> None:
    db = MagicMock()
    db.collection.return_value.stream.return_value = []

    summary = await sync_new_publications_for_all_users(
        db=db,
        email_service=MagicMock(),
        dry_run=False,
        settings=_make_settings(),
    )

    assert summary["users_processed"] == 0
    assert summary["works_added"] == 0

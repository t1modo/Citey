"""
Tests for citation_service helper functions and the date-filter / truncation
behaviour applied inside process_tracked_work.

Covers:
  - _normalize_title  (unicode-aware, newly rewritten)
  - _truncate         (newly added)
  - _dedup_key        (relies on _normalize_title)
  - publication_date filter  (missing dates skipped, stale dates skipped)
  - title / author truncation carried through to Notification objects
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models import TrackedWork
from app.services.citation_service import (
    _dedup_key,
    _normalize_title,
    _truncate,
    process_tracked_work,
)

_RECENT = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
_STALE = (datetime.now(tz=timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# _normalize_title
# ---------------------------------------------------------------------------


class TestNormalizeTitle:
    def test_ascii_lowercased_and_punctuation_stripped(self) -> None:
        assert _normalize_title("Hello, World!") == "helloworld"

    def test_accented_chars_map_to_ascii_base(self) -> None:
        # NFKD decomposes é → e + combining accent; combining mark is stripped
        assert _normalize_title("résumé") == "resume"

    def test_german_umlaut_mapped(self) -> None:
        assert _normalize_title("über") == "uber"

    def test_spanish_tilde_mapped(self) -> None:
        assert _normalize_title("señor") == "senor"

    def test_cjk_title_produces_nonempty_key(self) -> None:
        # Pure CJK must NOT collapse to "" (which would silently drop the paper)
        result = _normalize_title("深度学习方法")
        assert result != ""
        assert len(result) > 0

    def test_mixed_unicode_and_ascii(self) -> None:
        result = _normalize_title("Rôle de l'IA en 2024")
        assert "role" in result
        assert "ia" in result
        assert "2024" in result

    def test_whitespace_stripped(self) -> None:
        assert _normalize_title("deep  learning") == "deeplearning"

    def test_punctuation_only_returns_empty(self) -> None:
        assert _normalize_title("---!!!---") == ""

    def test_accented_and_plain_versions_normalize_equal(self) -> None:
        # "Résumé Based Learning" and "Resume Based Learning" share the same key
        assert _normalize_title("Résumé Based Learning") == _normalize_title("Resume Based Learning")

    def test_different_sources_same_title_equal(self) -> None:
        # Titles that are identical modulo encoding should dedup correctly
        assert _normalize_title("A Study on Naïve Bayes") == _normalize_title("A Study on Naive Bayes")


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_returned_unchanged(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_text_at_exact_limit_unchanged(self) -> None:
        text = "a" * 100
        assert _truncate(text, 100) == text

    def test_text_over_limit_gets_ellipsis(self) -> None:
        result = _truncate("a" * 400, 300)
        assert result.endswith("…")

    def test_truncated_length_is_limit_plus_ellipsis(self) -> None:
        result = _truncate("x" * 400, 300)
        assert len(result) == 301  # 300 chars + "…"

    def test_empty_string_unchanged(self) -> None:
        assert _truncate("", 100) == ""

    def test_unicode_ellipsis_not_three_dots(self) -> None:
        result = _truncate("x" * 50, 10)
        assert "…" in result
        assert "..." not in result


# ---------------------------------------------------------------------------
# _dedup_key
# ---------------------------------------------------------------------------


class TestDedupKey:
    def test_doi_preferred_over_title(self) -> None:
        assert _dedup_key({"doi": "10.1234/test", "title": "Some Title"}) == "doi:10.1234/test"

    def test_doi_lowercased(self) -> None:
        assert _dedup_key({"doi": "10.1234/TEST", "title": "x"}) == "doi:10.1234/test"

    def test_title_fallback_when_no_doi(self) -> None:
        key = _dedup_key({"doi": None, "title": "Deep Learning Methods"})
        assert key.startswith("title:")
        assert "deeplearningmethods" in key

    def test_empty_title_and_no_doi_returns_empty(self) -> None:
        assert _dedup_key({"doi": None, "title": ""}) == ""

    def test_missing_both_fields_returns_empty(self) -> None:
        assert _dedup_key({}) == ""

    def test_unicode_title_produces_nonempty_key(self) -> None:
        key = _dedup_key({"doi": None, "title": "深度学习方法"})
        assert key.startswith("title:")
        assert len(key) > len("title:")

    def test_accented_title_keys_match(self) -> None:
        k1 = _dedup_key({"doi": None, "title": "Résumé Learning"})
        k2 = _dedup_key({"doi": None, "title": "Resume Learning"})
        assert k1 == k2


# ---------------------------------------------------------------------------
# Minimal in-memory Firestore (self-contained for this test module)
# ---------------------------------------------------------------------------


class _FakeDocRef:
    def __init__(self, store: dict, path: str) -> None:
        self._store = store
        self._path = path
        self.id = path.rsplit("/", 1)[-1]

    def set(self, data: dict) -> None:
        self._store[self._path] = data

    def update(self, data: dict) -> None:
        self._store.setdefault(self._path, {}).update(data)

    def delete(self) -> None:
        self._store.pop(self._path, None)

    def collection(self, name: str) -> "_FakeCollRef":
        return _FakeCollRef(self._store, f"{self._path}/{name}")


class _FakeCollRef:
    def __init__(self, store: dict, prefix: str) -> None:
        self._store = store
        self._prefix = prefix

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, f"{self._prefix}/{doc_id}")

    def where(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return _FakeQuery()

    def stream(self):
        return iter([])


class _FakeQuery:
    def stream(self):
        return iter([])


class _FakeDB:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def collection(self, name: str) -> _FakeCollRef:
        return _FakeCollRef(self._store, name)

    def dump(self) -> dict:
        return dict(self._store)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture()
def tracked_work() -> TrackedWork:
    return TrackedWork(
        id="10.1038__nature12345",
        doi="10.1038/nature12345",
        openalex_id="W999",
        title="Test Work",
        authors=[],
        last_checked_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )


def _raw_citing_work(pub_date: str | None, *, doi: str = "10.1111/citing.0001") -> dict:
    """Build a minimal raw OpenAlex citing-work dict."""
    return {
        "id": f"https://openalex.org/W000001",
        "doi": f"https://doi.org/{doi}",
        "title": "A Citing Work",
        "publication_year": 2024,
        "publication_date": pub_date,
        "landing_page_url": None,
        "authorships": [],
    }


def _patch_oa_s2(oa_return: list, s2_return: list | None = None):
    return (
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            return_value=oa_return,
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=s2_return or [],
        ),
    )


# ---------------------------------------------------------------------------
# publication_date filter
# ---------------------------------------------------------------------------


async def test_paper_with_missing_pub_date_is_skipped(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Papers with no publication_date must be excluded — they cannot be date-verified."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(None)])
    with oa_patch, s2_patch:
        count, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert count == 0
    assert notifications == []


async def test_paper_with_stale_pub_date_is_skipped(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Papers published more than 30 days ago are filtered out."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(_STALE)])
    with oa_patch, s2_patch:
        count, _ = await process_tracked_work("uid1", tracked_work, fake_db, dry_run=False)
    assert count == 0


async def test_paper_with_recent_pub_date_is_kept(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Papers published within the last 30 days pass the date filter."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(_RECENT)])
    with oa_patch, s2_patch:
        count, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert count == 1
    assert len(notifications) == 1


async def test_mix_of_dated_and_undated_papers(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Only papers with a recent date are written; others are silently dropped."""
    works = [
        _raw_citing_work(_RECENT, doi="10.1111/keep.001"),
        _raw_citing_work(None, doi="10.1111/drop.002"),
        _raw_citing_work(_STALE, doi="10.1111/drop.003"),
    ]
    oa_patch, s2_patch = _patch_oa_s2(works)
    with oa_patch, s2_patch:
        count, _ = await process_tracked_work("uid1", tracked_work, fake_db, dry_run=False)
    assert count == 1


# ---------------------------------------------------------------------------
# Title / author truncation
# ---------------------------------------------------------------------------


async def test_notification_title_truncated(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Citing-work titles over 300 characters are truncated with '…'."""
    long_title = "B" * 400
    raw = [{**_raw_citing_work(_RECENT, doi="10.1111/long"), "title": long_title}]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert len(notifications) == 1
    assert notifications[0].citing_work_title.endswith("…")
    assert len(notifications[0].citing_work_title) <= 301  # 300 chars + "…"


async def test_notification_title_within_limit_unchanged(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Titles at or under the 300-character limit are stored as-is."""
    normal_title = "A Normal Academic Title"
    raw = [{**_raw_citing_work(_RECENT, doi="10.1111/normal"), "title": normal_title}]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert notifications[0].citing_work_title == normal_title


async def test_author_names_truncated(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """Author names over 100 characters are truncated with '…'."""
    long_name = "X" * 150
    raw = [{
        **_raw_citing_work(_RECENT, doi="10.1111/auth"),
        "authorships": [{"author": {"display_name": long_name}, "institutions": []}],
    }]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert len(notifications) == 1
    for author in notifications[0].citing_authors:
        assert len(author) <= 101  # 100 chars + "…"
        assert author.endswith("…")


async def test_partial_async_failure_still_returns_surviving_source(
    fake_db: _FakeDB, tracked_work: TrackedWork
) -> None:
    """If OA raises an exception, S2 results are still returned (and vice versa)."""
    s2_paper = {
        "paperId": "s2abc",
        "externalIds": {"DOI": "10.9999/s2only"},
        "title": "S2 Survivor",
        "year": 2024,
        "authors": [],
        "publicationDate": _RECENT,
    }
    with (
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            side_effect=RuntimeError("OA exploded"),
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=[s2_paper],
        ),
    ):
        count, notifications = await process_tracked_work(
            "uid1", tracked_work, fake_db, dry_run=False
        )
    assert count == 1
    assert notifications[0].citing_work_title == "S2 Survivor"

"""
Tests for citation_service helper functions and the date-filter / truncation
behaviour applied inside process_tracked_work.

Covers:
  - _normalize_title  (unicode-aware, newly rewritten)
  - _truncate         (newly added)
  - _dedup_key        (relies on _normalize_title)
  - publication_date filter  (missing dates skipped, stale dates kept quiet)
  - title / author truncation carried through to Notification objects

The process_tracked_work tests run against the test database
(TEST_DATABASE_URL; skipped otherwise).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Work
from app.schemas import TrackedWork
from app.services import alert_service, tracking_service
from app.services.citation_service import (
    _dedup_key,
    _normalize_title,
    _truncate,
    process_tracked_work,
    run_job_for_user,
)
from app.store import CitationStore, UserStore, WorkStore
from tests.conftest import needs_db

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
# Shared fixtures
# ---------------------------------------------------------------------------

_LAST_CHECKED = datetime(2020, 1, 1, tzinfo=timezone.utc)


async def _track(session, key: str, fields: dict) -> Work:
    await UserStore(session).create("uid1", email="uid1@uni.edu")
    work, _ = await tracking_service.track_paper(
        session, "uid1", key, fields, now=datetime.now(tz=timezone.utc)
    )
    return work


@pytest.fixture()
async def tracked_work(pg_session) -> Work:
    """A paper uid1 tracks; its first check (the baseline) is still to come."""
    return await _track(pg_session, "10.1038__nature12345", {
        "doi": "10.1038/nature12345",
        "openalex_id": "W999",
        "title": "Test Work",
        "authors": [],
        "last_checked_at": _LAST_CHECKED,
    })


async def _alerted(session) -> list[str | None]:
    """DOIs of uid1's alerts."""
    return [n.citing_work_doi for n in await alert_service.notifications(session, "uid1")]


def _raw_citing_work(pub_date: str | None, *, doi: str = "10.1111/citing.0001") -> dict:
    """Build a minimal raw OpenAlex citing-work dict."""
    return {
        "id": "https://openalex.org/W000001",
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


@needs_db
async def test_paper_with_missing_pub_date_is_skipped(pg_session, tracked_work: Work) -> None:
    """A paper with no publication_date and an old year is outside the window:
    not reported and not recorded."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(None)])
    with oa_patch, s2_patch:
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count == 0
    assert notifications == []
    assert await _alerted(pg_session) == []
    assert await CitationStore(pg_session).known_keys(tracked_work.id) == set()


@needs_db
async def test_paper_with_stale_pub_date_is_skipped(pg_session, tracked_work: Work) -> None:
    """At the baseline, papers published more than 30 days ago are recorded
    as known but not reported."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(_STALE)])
    with oa_patch, s2_patch:
        count, _ = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count == 0
    assert await _alerted(pg_session) == []
    assert "doi:10.1111/citing.0001" in await CitationStore(pg_session).known_keys(tracked_work.id)


@needs_db
async def test_paper_with_recent_pub_date_is_kept(pg_session, tracked_work: Work) -> None:
    """Papers published within the last 30 days pass the date filter."""
    oa_patch, s2_patch = _patch_oa_s2([_raw_citing_work(_RECENT)])
    with oa_patch, s2_patch:
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count == 1
    assert len(notifications) == 1
    assert await _alerted(pg_session) == ["10.1111/citing.0001"]


@needs_db
async def test_mix_of_dated_and_undated_papers(pg_session, tracked_work: Work) -> None:
    """Only papers with a recent date are alerted; others are silently dropped."""
    works = [
        _raw_citing_work(_RECENT, doi="10.1111/keep.001"),
        _raw_citing_work(None, doi="10.1111/drop.002"),
        _raw_citing_work(_STALE, doi="10.1111/drop.003"),
    ]
    oa_patch, s2_patch = _patch_oa_s2(works)
    with oa_patch, s2_patch:
        count, _ = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count == 1
    assert await _alerted(pg_session) == ["10.1111/keep.001"]


# ---------------------------------------------------------------------------
# Title / author truncation
# ---------------------------------------------------------------------------


@needs_db
async def test_notification_title_truncated(pg_session, tracked_work: Work) -> None:
    """Citing-work titles over 300 characters are truncated with '…'."""
    long_title = "B" * 400
    raw = [{**_raw_citing_work(_RECENT, doi="10.1111/long"), "title": long_title}]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert len(notifications) == 1
    assert notifications[0].citing_work_title.endswith("…")
    assert len(notifications[0].citing_work_title) <= 301  # 300 chars + "…"
    [stored] = await alert_service.notifications(pg_session, "uid1")
    assert stored.citing_work_title == notifications[0].citing_work_title


@needs_db
async def test_notification_title_within_limit_unchanged(pg_session, tracked_work: Work) -> None:
    """Titles at or under the 300-character limit are stored as-is."""
    normal_title = "A Normal Academic Title"
    raw = [{**_raw_citing_work(_RECENT, doi="10.1111/normal"), "title": normal_title}]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert notifications[0].citing_work_title == normal_title
    [stored] = await alert_service.notifications(pg_session, "uid1")
    assert stored.citing_work_title == normal_title


@needs_db
async def test_author_names_truncated(pg_session, tracked_work: Work) -> None:
    """Author names over 100 characters are truncated with '…'."""
    long_name = "X" * 150
    raw = [{
        **_raw_citing_work(_RECENT, doi="10.1111/auth"),
        "authorships": [{"author": {"display_name": long_name}, "institutions": []}],
    }]
    oa_patch, s2_patch = _patch_oa_s2(raw)
    with oa_patch, s2_patch:
        _, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert len(notifications) == 1
    [stored] = await alert_service.notifications(pg_session, "uid1")
    assert stored.citing_authors == notifications[0].citing_authors
    assert notifications[0].citing_authors
    for author in notifications[0].citing_authors:
        assert len(author) <= 101  # 100 chars + "…"
        assert author.endswith("…")


@needs_db
async def test_partial_async_failure_still_returns_surviving_source(pg_session, tracked_work: Work) -> None:
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
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count == 1
    assert notifications[0].citing_work_title == "S2 Survivor"
    assert await _alerted(pg_session) == ["10.9999/s2only"]


# ---------------------------------------------------------------------------
# Source failures are recorded, not mistaken for "no citations"
# ---------------------------------------------------------------------------


@needs_db
async def test_one_source_failing_is_recorded_and_other_source_still_counts(
    pg_session, tracked_work: Work
) -> None:
    """S2 down: the failure is stored on the paper, OpenAlex's citation still
    counts, and the paper counts as checked."""
    from app.services.source_errors import SourceUnavailable

    failures: list[str] = []
    with patch(
        "app.services.citation_service.openalex_svc.get_citing_works",
        new_callable=AsyncMock, return_value=[_raw_citing_work(_RECENT)],
    ), patch(
        "app.services.citation_service.s2_svc.get_citing_papers",
        new_callable=AsyncMock, side_effect=SourceUnavailable("semantic_scholar", "429"),
    ):
        count, _ = await process_tracked_work(pg_session, tracked_work, source_failures=failures)
    assert count == 1
    assert failures == ["semantic_scholar"]
    stored = await WorkStore(pg_session).refresh(tracked_work)
    assert stored.last_check_failed_sources == ["semantic_scholar"]
    assert stored.last_checked_at > _LAST_CHECKED


@needs_db
async def test_all_sources_failing_leaves_last_checked_untouched(pg_session, tracked_work: Work) -> None:
    """Both main sources down: nothing was checked, so last_checked_at stays."""
    from app.services.source_errors import SourceUnavailable

    with patch(
        "app.services.citation_service.openalex_svc.get_citing_works",
        new_callable=AsyncMock, side_effect=SourceUnavailable("openalex", "503"),
    ), patch(
        "app.services.citation_service.s2_svc.get_citing_papers",
        new_callable=AsyncMock, side_effect=SourceUnavailable("semantic_scholar", "429"),
    ):
        count, _ = await process_tracked_work(pg_session, tracked_work)
    assert count == 0
    stored = await WorkStore(pg_session).refresh(tracked_work)
    assert sorted(stored.last_check_failed_sources) == ["openalex", "semantic_scholar"]
    assert stored.last_checked_at == _LAST_CHECKED


@needs_db
async def test_foreign_openalex_id_is_resolved_by_doi(pg_session) -> None:
    """A paper imported with "S2:…" in openalex_id must be looked up by DOI,
    not sent to OpenAlex as cites:S2:…"""
    work = await _track(pg_session, "10.48550__arxiv.2506.02005", {
        "doi": "10.48550/arXiv.2506.02005",
        "openalex_id": "S2:d33be425820b25e970b0c35d00eb9ef563a7b873",
        "title": "A preprint",
        "last_checked_at": _LAST_CHECKED,
    })

    citing = AsyncMock(return_value=[])
    mail = MagicMock(send_digest_email=AsyncMock())
    with patch(
        "app.services.citation_service.openalex_svc.get_work_by_doi",
        new_callable=AsyncMock, return_value={"id": "https://openalex.org/W42"},
    ), patch(
        "app.services.citation_service.openalex_svc.get_citing_works", citing,
    ), patch(
        "app.services.citation_service.s2_svc.get_citing_papers",
        new_callable=AsyncMock, return_value=[],
    ), patch(
        "app.services.citation_service.openalex_svc.get_citation_counts",
        new_callable=AsyncMock, return_value={},
    ), patch(
        "app.services.semantic_scholar.get_citation_counts",
        new_callable=AsyncMock, return_value={},
    ):
        await run_job_for_user("uid1", pg_session, mail, settings=MagicMock())

    assert citing.await_args.args[0] == "https://openalex.org/W42"
    assert (await WorkStore(pg_session).refresh(work)).openalex_id == "https://openalex.org/W42"


def test_foreign_openalex_id_is_dropped_by_the_api_model() -> None:
    """The API shape never shows an "S2:…" ID as an OpenAlex ID."""
    work = TrackedWork(id="x", title="A preprint", openalex_id="S2:d33be425820b25e970b0c35d00eb9ef563a7b873")
    assert work.openalex_id is None


def test_titles_and_names_are_cleaned_on_the_model() -> None:
    work = TrackedWork(
        id="x", title="<i>E. coli</i> &amp; H<sub>2</sub>O",
        authors=["Jane Smith 0001", "Erd\\H{o}s"], venue="arXiv &amp; more",
    )
    assert work.title == "E. coli & H₂O"
    assert work.authors == ["Jane Smith", "Erdős"]
    assert work.venue == "arXiv & more"

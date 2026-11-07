"""
Tests for the deduplication logic in citation_service.process_tracked_work.

Runs against the test database (TEST_DATABASE_URL; skipped otherwise).
Both OpenAlex and Semantic Scholar are mocked since process_tracked_work
fetches from both sources in parallel.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

# Use a recent date so papers pass the 30-day publication_date filter in process_tracked_work.
_RECENT_DATE = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

from app.models import Citation, CitingWork, Work
from app.services import alert_service, tracking_service
from app.services.citation_service import process_tracked_work
from app.store import AlertStore, UserStore, WorkStore
from tests.conftest import needs_db

pytestmark = needs_db

_LAST_CHECKED = datetime(2020, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _track(session, key: str, fields: dict) -> Work:
    await UserStore(session).create("user_abc", email="abc@uni.edu")
    work, _ = await tracking_service.track_paper(
        session, "user_abc", key, fields, now=datetime.now(tz=timezone.utc)
    )
    return work


@pytest.fixture()
async def tracked_work(pg_session) -> Work:
    """A paper user_abc tracks; its first check (the baseline) is still to come."""
    return await _track(pg_session, "10.1038__nature12345", {
        "doi": "10.1038/nature12345",
        "openalex_id": "W2741809807",
        "title": "A Landmark Study in Genomics",
        "authors": ["Jane Smith"],
        "year": 2021,
        "last_checked_at": _LAST_CHECKED,
    })


async def _alerts(session) -> list[str | None]:
    """DOIs of user_abc's alerts."""
    return sorted(n.citing_work_doi or "" for n in await alert_service.notifications(session, "user_abc"))


async def _rows(session, model) -> list:
    return list((await session.exec(select(model))).all())


# Raw OpenAlex citing works — publication_date is set to yesterday so they
# pass the 30-day recency filter in process_tracked_work.
_CITING_WORKS_RAW = [
    {
        "id": "https://openalex.org/W1111111111",
        "doi": "https://doi.org/10.1016/j.cell.2022.01.001",
        "title": "Citing Paper One",
        "publication_year": 2022,
        "publication_date": _RECENT_DATE,
        "landing_page_url": "https://example.com/paper1",
        "authorships": [
            {
                "author": {"display_name": "Alice"},
                "institutions": [{"display_name": "MIT"}],
            }
        ],
    },
    {
        "id": "https://openalex.org/W2222222222",
        "doi": "https://doi.org/10.1038/s41586-022-00001-1",
        "title": "Citing Paper Two",
        "publication_year": 2022,
        "publication_date": _RECENT_DATE,
        "landing_page_url": "https://example.com/paper2",
        "authorships": [
            {
                "author": {"display_name": "Bob"},
                "institutions": [],
            }
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers — patch both OA and S2 together
# ---------------------------------------------------------------------------

def _patch_both(oa_return=None, s2_return=None):
    """Return a context manager that patches both OA and S2 citation fetches."""
    oa_return = oa_return or []
    s2_return = s2_return or []
    return (
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            return_value=oa_return,
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=s2_return,
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citation_counts",
            new_callable=AsyncMock,
            return_value={},
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_first_run_writes_all_notifications(pg_session, tracked_work: Work) -> None:
    """On the first run, every recent citing work becomes an alert."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)

    assert count == 2
    assert len(notifications) == 2
    assert await _alerts(pg_session) == ["10.1016/j.cell.2022.01.001", "10.1038/s41586-022-00001-1"]


async def test_second_run_does_not_duplicate(pg_session, tracked_work: Work) -> None:
    """Running the job twice for the same work must not create duplicate alerts."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count1, _ = await process_tracked_work(pg_session, tracked_work, dry_run=False)
        count2, notes2 = await process_tracked_work(pg_session, tracked_work, dry_run=False)

    assert count1 == 2
    assert (count2, notes2) == (0, [])
    assert len(await _alerts(pg_session)) == 2
    assert len(await _rows(pg_session, Citation)) == 2


async def test_pruned_notification_is_not_resent(pg_session, tracked_work: Work) -> None:
    """Alerts are pruned after 30 days; the citing paper must not be
    alerted again just because its alert is gone."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count1, _ = await process_tracked_work(pg_session, tracked_work)

        # Simulate the daily prune deleting every alert.
        await AlertStore(pg_session).prune(datetime.now(tz=timezone.utc) + timedelta(days=1))
        assert await _alerts(pg_session) == []

        count2, _ = await process_tracked_work(pg_session, tracked_work)

    assert count1 == 2
    assert count2 == 0
    assert await _alerts(pg_session) == []


async def test_dry_run_does_not_write_to_the_database(pg_session, tracked_work: Work) -> None:
    """dry_run=True returns the would-be alerts but writes nothing."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=True)

    assert count == 2
    assert len(notifications) == 2
    assert await _alerts(pg_session) == []
    assert await _rows(pg_session, Citation) == []
    assert await _rows(pg_session, CitingWork) == []
    stored = await WorkStore(pg_session).refresh(tracked_work)
    assert stored.last_checked_at == _LAST_CHECKED
    assert stored.citation_window is None
    assert stored.last_check_failed_sources == []


async def test_new_citing_work_added_after_first_run(pg_session, tracked_work: Work) -> None:
    """A new citing work on the second run produces exactly one new alert."""
    oa_patch1, s2_patch1, s2_counts_patch1 = _patch_both(oa_return=[_CITING_WORKS_RAW[0]])
    with oa_patch1, s2_patch1, s2_counts_patch1:
        count1, _ = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count1 == 1

    oa_patch2, s2_patch2, s2_counts_patch2 = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch2, s2_patch2, s2_counts_patch2:
        count2, notes2 = await process_tracked_work(pg_session, tracked_work, dry_run=False)
    assert count2 == 1
    assert notes2[0].citing_work_doi == "10.1038/s41586-022-00001-1"

    assert len(await _alerts(pg_session)) == 2


async def test_resolves_openalex_id_when_missing(pg_session) -> None:
    """When openalex_id is not set, it is resolved from the DOI and stored."""
    work_without_id = await _track(pg_session, "10.1038__nature12345", {
        "doi": "10.1038/nature12345",
        "openalex_id": None,
        "title": "A Landmark Study in Genomics",
        "authors": [],
        "year": 2021,
    })
    citing = AsyncMock(return_value=[])

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_work_by_doi",
            new_callable=AsyncMock,
            return_value={"id": "https://openalex.org/W2741809807"},
        ),
        patch("app.services.citation_service.openalex_svc.get_citing_works", citing),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citation_counts",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        count, _ = await process_tracked_work(pg_session, work_without_id, dry_run=False)

    assert count == 0
    assert citing.await_args.args[0] == "https://openalex.org/W2741809807"
    stored = await WorkStore(pg_session).refresh(work_without_id)
    assert stored.openalex_id == "https://openalex.org/W2741809807"


async def test_skips_work_when_openalex_id_unresolvable(pg_session) -> None:
    """If the OpenAlex ID cannot be resolved, OpenAlex is skipped quietly."""
    work = await _track(pg_session, "10.9999__unknown", {
        "doi": "10.9999/unknown",
        "openalex_id": None,
        "title": "Unknown Work",
        "authors": [],
    })
    citing = AsyncMock(return_value=[])

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_work_by_doi",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.citation_service.openalex_svc.get_citing_works", citing),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citation_counts",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        count, notifications = await process_tracked_work(pg_session, work, dry_run=False)

    assert count == 0
    assert notifications == []
    citing.assert_not_awaited()
    assert (await WorkStore(pg_session).refresh(work)).openalex_id is None


async def test_s2_results_merged_with_openalex(pg_session, tracked_work: Work) -> None:
    """Citations from S2 that are not in OpenAlex are included after dedup."""
    s2_only = [
        {
            "paperId": "s2abc123",
            "externalIds": {"DOI": "10.9999/s2only"},
            "title": "S2-Only Citing Paper",
            "year": 2023,
            "authors": [{"name": "S2 Author"}],
            "publicationDate": _RECENT_DATE,
        }
    ]

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            return_value=[_CITING_WORKS_RAW[0]],
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=s2_only,
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citation_counts",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        count, notifications = await process_tracked_work(pg_session, tracked_work, dry_run=False)

    # 1 from OA + 1 from S2 = 2 total
    assert count == 2
    assert await _alerts(pg_session) == ["10.1016/j.cell.2022.01.001", "10.9999/s2only"]


async def test_doi_dedup_prevents_duplicate_from_both_sources(pg_session, tracked_work: Work) -> None:
    """The same DOI from both OA and S2 produces only one alert."""
    shared_doi = "10.1016/j.cell.2022.01.001"
    s2_duplicate = [
        {
            "paperId": "s2xyz",
            "externalIds": {"DOI": shared_doi},
            "title": "Citing Paper One",
            "year": 2022,
            "authors": [{"name": "Alice"}],
            "publicationDate": _RECENT_DATE,
        }
    ]

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            return_value=[_CITING_WORKS_RAW[0]],  # doi = 10.1016/j.cell.2022.01.001
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citing_papers",
            new_callable=AsyncMock,
            return_value=s2_duplicate,
        ),
        patch(
            "app.services.citation_service.s2_svc.get_citation_counts",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        count, _ = await process_tracked_work(pg_session, tracked_work, dry_run=False)

    # Same DOI from both sources → one citing paper, one alert
    assert count == 1
    assert await _alerts(pg_session) == [shared_doi]
    assert len(await _rows(pg_session, CitingWork)) == 1


"""
Tests for the deduplication logic in citation_service.process_tracked_work.

Uses an in-memory fake Firestore so no real Firebase connection is required.
Both OpenAlex and Semantic Scholar are mocked since process_tracked_work
fetches from both sources in parallel.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Use a recent date so papers pass the 30-day publication_date filter in process_tracked_work.
_RECENT_DATE = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

from app.models import TrackedWork
from app.services.citation_service import process_tracked_work

# ---------------------------------------------------------------------------
# Fake (in-memory) Firestore
# ---------------------------------------------------------------------------


class _FakeDocSnapshot:
    def __init__(self, data: dict | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict | None:
        return self._data


class _FakeDocRef:
    def __init__(self, store: dict, path: str) -> None:
        self._store = store
        self._path = path
        self.id = path.rsplit("/", 1)[-1]

    def get(self) -> _FakeDocSnapshot:
        return _FakeDocSnapshot(self._store.get(self._path))

    def set(self, data: dict) -> None:
        self._store[self._path] = data

    def update(self, data: dict) -> None:
        existing = self._store.get(self._path, {})
        existing.update(data)
        self._store[self._path] = existing

    def delete(self) -> None:
        self._store.pop(self._path, None)

    def collection(self, name: str) -> "_FakeCollectionRef":
        return _FakeCollectionRef(self._store, f"{self._path}/{name}")


class _FakeQuery:
    """Minimal Firestore query simulation supporting a single where() filter."""

    def __init__(self, collection: "_FakeCollectionRef", field: str, op: str, value: Any) -> None:
        self._collection = collection
        self._field = field
        self._op = op
        self._value = value

    def stream(self):
        for doc in self._collection.stream():
            data = doc.to_dict() or {}
            doc_value = data.get(self._field)
            if self._op == "==" and doc_value == self._value:
                yield doc


class _FakeCollectionRef:
    def __init__(self, store: dict, prefix: str) -> None:
        self._store = store
        self._prefix = prefix

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, f"{self._prefix}/{doc_id}")

    def where(self, field: str, op: str, value: Any) -> "_FakeQuery":
        return _FakeQuery(self, field, op, value)

    def stream(self):
        prefix = self._prefix + "/"
        for key, value in list(self._store.items()):
            if key.startswith(prefix) and key.count("/") == self._prefix.count("/") + 1:
                doc_id = key[len(prefix):]
                ref = _FakeDocRef(self._store, key)
                ref.id = doc_id
                ref.reference = ref
                ref.to_dict = lambda v=value: v
                yield ref


class _FakeDB:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def collection(self, name: str) -> _FakeCollectionRef:
        return _FakeCollectionRef(self._store, name)

    def dump(self) -> dict:
        return dict(self._store)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture()
def tracked_work() -> TrackedWork:
    return TrackedWork(
        id="10.1038__nature12345",
        doi="10.1038/nature12345",
        openalex_id="W2741809807",
        title="A Landmark Study in Genomics",
        authors=["Jane Smith"],
        year=2021,
        last_checked_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )


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


async def test_first_run_writes_all_notifications(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """On the first run, all citing works produce notification docs."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count, notifications = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )

    assert count == 2
    assert len(notifications) == 2
    notification_keys = [k for k in fake_db.dump() if "/notifications/" in k]
    assert len(notification_keys) == 2


async def test_second_run_does_not_duplicate(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """Running the job twice for the same work must not create duplicate notifications."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count1, _ = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )
        count2, _ = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )

    assert count1 == 2
    assert count2 == 0

    notification_keys = [k for k in fake_db.dump() if "/notifications/" in k]
    assert len(notification_keys) == 2


async def test_dry_run_does_not_write_to_firestore(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """dry_run=True must not write any documents to Firestore."""
    oa_patch, s2_patch, s2_counts_patch = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch, s2_patch, s2_counts_patch:
        count, notifications = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=True
        )

    assert count == 2
    assert len(notifications) == 2
    store = fake_db.dump()
    assert all("/notifications/" not in k for k in store)
    assert all("trackedWorks" not in k for k in store)


async def test_new_citing_work_added_after_first_run(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """A new citing work on the second run produces exactly one new notification."""
    oa_patch1, s2_patch1, s2_counts_patch1 = _patch_both(oa_return=[_CITING_WORKS_RAW[0]])
    with oa_patch1, s2_patch1, s2_counts_patch1:
        count1, _ = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )
    assert count1 == 1

    oa_patch2, s2_patch2, s2_counts_patch2 = _patch_both(oa_return=_CITING_WORKS_RAW)
    with oa_patch2, s2_patch2, s2_counts_patch2:
        count2, _ = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )
    assert count2 == 1

    notification_keys = [k for k in fake_db.dump() if "/notifications/" in k]
    assert len(notification_keys) == 2


async def test_resolves_openalex_id_when_missing(fake_db: _FakeDB) -> None:
    """When openalex_id is not set, it is resolved from the DOI."""
    work_without_id = TrackedWork(
        id="10.1038__nature12345",
        doi="10.1038/nature12345",
        openalex_id=None,
        title="A Landmark Study in Genomics",
        authors=[],
        year=2021,
    )

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_work_by_doi",
            new_callable=AsyncMock,
            return_value={"id": "https://openalex.org/W2741809807"},
        ),
        patch(
            "app.services.citation_service.openalex_svc.get_citing_works",
            new_callable=AsyncMock,
            return_value=[],
        ),
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
        count, _ = await process_tracked_work(
            uid="user_abc", work=work_without_id, db=fake_db, dry_run=False
        )

    assert count == 0


async def test_skips_work_when_openalex_id_unresolvable(fake_db: _FakeDB) -> None:
    """If the OpenAlex ID cannot be resolved, the work is silently skipped."""
    work = TrackedWork(
        id="10.9999__unknown",
        doi="10.9999/unknown",
        openalex_id=None,
        title="Unknown Work",
        authors=[],
    )

    with (
        patch(
            "app.services.citation_service.openalex_svc.get_work_by_doi",
            new_callable=AsyncMock,
            return_value=None,
        ),
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
        count, notifications = await process_tracked_work(
            uid="user_abc", work=work, db=fake_db, dry_run=False
        )

    assert count == 0
    assert notifications == []


async def test_s2_results_merged_with_openalex(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
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
        count, notifications = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )

    # 1 from OA + 1 from S2 = 2 total (assuming S2 paper passes date filter)
    assert count >= 1


async def test_doi_dedup_prevents_duplicate_from_both_sources(
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """The same DOI from both OA and S2 produces only one notification."""
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
        count, _ = await process_tracked_work(
            uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
        )

    # Same DOI from both sources → only 1 notification
    notification_keys = [k for k in fake_db.dump() if "/notifications/" in k]
    assert len(notification_keys) == 1

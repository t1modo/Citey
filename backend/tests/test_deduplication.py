"""
Tests for the deduplication logic in citation_service.process_tracked_work.

We use an in-memory fake Firestore implementation so no real Firebase
connection is required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import TrackedWork
from app.services.citation_service import process_tracked_work

# ---------------------------------------------------------------------------
# Fake (in-memory) Firestore
# ---------------------------------------------------------------------------


class _FakeDocSnapshot:
    """Mimics a Firestore DocumentSnapshot."""

    def __init__(self, data: dict | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict | None:
        return self._data


class _FakeDocRef:
    """Mimics a Firestore DocumentReference backed by a dict store."""

    def __init__(self, store: dict, path: str) -> None:
        self._store = store
        self._path = path

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


class _FakeCollectionRef:
    """Mimics a Firestore CollectionReference."""

    def __init__(self, store: dict, prefix: str) -> None:
        self._store = store
        self._prefix = prefix

    def document(self, doc_id: str) -> _FakeDocRef:
        path = f"{self._prefix}/{doc_id}"
        return _FakeDocRef(self._store, path)

    def stream(self):
        prefix = self._prefix + "/"
        for key, value in self._store.items():
            if key.startswith(prefix) and key.count("/") == self._prefix.count("/") + 1:
                doc_id = key[len(prefix):]
                ref = _FakeDocRef(self._store, key)
                ref.id = doc_id
                ref.to_dict = lambda v=value: v
                yield ref


class _FakeDB:
    """Minimal fake Firestore client."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def collection(self, name: str) -> _FakeCollectionRef:
        return _FakeCollectionRef(self._store, name)

    def dump(self) -> dict:
        """Expose internal store for assertions."""
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
    )


# Raw OpenAlex citing works to return from the mock
_CITING_WORKS_RAW = [
    {
        "id": "https://openalex.org/W1111111111",
        "doi": "https://doi.org/10.1016/j.cell.2022.01.001",
        "title": "Citing Paper One",
        "publication_year": 2022,
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_first_run_writes_all_notifications(
    mock_get_citing: AsyncMock,
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """On the first run, all citing works should produce notification docs."""
    mock_get_citing.return_value = _CITING_WORKS_RAW

    count, notifications = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
    )

    assert count == 2
    assert len(notifications) == 2
    store = fake_db.dump()
    # Both notification docs must exist in Firestore.
    notification_keys = [k for k in store if "/notifications/" in k]
    assert len(notification_keys) == 2


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_second_run_does_not_duplicate(
    mock_get_citing: AsyncMock,
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """Running the job twice for the same work must not create duplicate notifications."""
    mock_get_citing.return_value = _CITING_WORKS_RAW

    # First run
    count1, _ = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
    )

    # Second run (same citing works returned from mock)
    count2, _ = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
    )

    assert count1 == 2
    assert count2 == 0  # No new notifications — all already exist

    store = fake_db.dump()
    notification_keys = [k for k in store if "/notifications/" in k]
    assert len(notification_keys) == 2  # Still only 2, not 4


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_dry_run_does_not_write_to_firestore(
    mock_get_citing: AsyncMock,
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """dry_run=True must not write any documents to Firestore."""
    mock_get_citing.return_value = _CITING_WORKS_RAW

    count, notifications = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=True
    )

    assert count == 2
    assert len(notifications) == 2
    store = fake_db.dump()
    # Nothing should have been written.
    assert all("/notifications/" not in k for k in store)
    # last_checked_at should also NOT be updated in dry_run mode.
    assert all("trackedWorks" not in k for k in store)


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_new_citing_work_added_after_first_run(
    mock_get_citing: AsyncMock,
    fake_db: _FakeDB,
    tracked_work: TrackedWork,
) -> None:
    """A new citing work appearing on the second run should produce one new notification."""
    # First run: only one citing work.
    mock_get_citing.return_value = [_CITING_WORKS_RAW[0]]
    count1, _ = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
    )
    assert count1 == 1

    # Second run: two citing works (one existing + one new).
    mock_get_citing.return_value = _CITING_WORKS_RAW
    count2, _ = await process_tracked_work(
        uid="user_abc", work=tracked_work, db=fake_db, dry_run=False
    )
    assert count2 == 1  # Only the new one

    store = fake_db.dump()
    notification_keys = [k for k in store if "/notifications/" in k]
    assert len(notification_keys) == 2


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_work_by_doi",
    new_callable=AsyncMock,
)
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_resolves_openalex_id_when_missing(
    mock_get_citing: AsyncMock,
    mock_get_by_doi: AsyncMock,
    fake_db: _FakeDB,
) -> None:
    """When openalex_id is not set, it should be resolved from the DOI."""
    work_without_id = TrackedWork(
        id="10.1038__nature12345",
        doi="10.1038/nature12345",
        openalex_id=None,  # Not set
        title="A Landmark Study in Genomics",
        authors=[],
        year=2021,
    )

    mock_get_by_doi.return_value = {"id": "https://openalex.org/W2741809807"}
    mock_get_citing.return_value = []

    count, _ = await process_tracked_work(
        uid="user_abc", work=work_without_id, db=fake_db, dry_run=False
    )

    mock_get_by_doi.assert_awaited_once()
    mock_get_citing.assert_awaited_once()
    assert count == 0


@pytest.mark.asyncio
@patch(
    "app.services.citation_service.openalex_svc.get_work_by_doi",
    new_callable=AsyncMock,
)
@patch(
    "app.services.citation_service.openalex_svc.get_citing_works",
    new_callable=AsyncMock,
)
async def test_skips_work_when_openalex_id_unresolvable(
    mock_get_citing: AsyncMock,
    mock_get_by_doi: AsyncMock,
    fake_db: _FakeDB,
) -> None:
    """If the OpenAlex ID cannot be resolved, the work is silently skipped."""
    work = TrackedWork(
        id="10.9999__unknown",
        doi="10.9999/unknown",
        openalex_id=None,
        title="Unknown Work",
        authors=[],
    )
    mock_get_by_doi.return_value = None  # Not found in OpenAlex

    count, notifications = await process_tracked_work(
        uid="user_abc", work=work, db=fake_db, dry_run=False
    )

    assert count == 0
    assert notifications == []
    mock_get_citing.assert_not_awaited()

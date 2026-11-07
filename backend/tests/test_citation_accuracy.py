"""
Late indexed citations, duplicate and junk alerts, and reliable alert emails.

Each test pins one way the nightly check used to report the wrong thing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from citey.models import TrackedWork
from citey.services.citation_service import (
    _CITATION_WINDOW_VERSION,
    process_tracked_work,
    run_job_for_user,
)
from citey.services.citing_identity import identity_keys, is_junk, merge_records, title_key

_NOW = datetime.now(tz=timezone.utc)


def _day(days_ago: int) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# A small Firestore fake with equality filters and real batches
# ---------------------------------------------------------------------------


class _Doc:
    def __init__(self, store: dict, path: str) -> None:
        self._store, self._path = store, path
        self.id = path.rsplit("/", 1)[-1]
        self.reference = self

    @property
    def exists(self) -> bool:
        return self._path in self._store

    def get(self) -> "_Doc":
        return self

    def to_dict(self) -> dict:
        return dict(self._store.get(self._path, {}))

    def set(self, data: dict, merge: bool = False) -> None:
        if merge:
            self._store.setdefault(self._path, {}).update(data)
        else:
            self._store[self._path] = dict(data)

    def update(self, data: dict) -> None:
        self._store.setdefault(self._path, {}).update(data)

    def delete(self) -> None:
        self._store.pop(self._path, None)

    def collection(self, name: str) -> "_Coll":
        return _Coll(self._store, f"{self._path}/{name}")


class _Coll:
    def __init__(self, store: dict, prefix: str, filters: tuple = ()) -> None:
        self._store, self._prefix, self._filters = store, prefix, filters

    def document(self, doc_id: str) -> _Doc:
        return _Doc(self._store, f"{self._prefix}/{doc_id}")

    def where(self, field: str, op: str, value: Any) -> "_Coll":
        assert op == "=="
        return _Coll(self._store, self._prefix, self._filters + ((field, value),))

    def select(self, _fields: list) -> "_Coll":
        return self

    def stream(self):
        depth = self._prefix.count("/") + 1
        for path in list(self._store):
            if path.startswith(self._prefix + "/") and path.count("/") == depth:
                data = self._store[path]
                if all(data.get(f) == v for f, v in self._filters):
                    yield _Doc(self._store, path)


class _Batch:
    def __init__(self) -> None:
        self.ops: list = []

    def set(self, ref, data) -> None:
        self.ops.append(lambda: ref.set(data))

    def update(self, ref, data) -> None:
        self.ops.append(lambda: ref.update(data))

    def delete(self, ref) -> None:
        self.ops.append(ref.delete)

    def commit(self) -> None:
        for op in self.ops:
            op()


class _DB:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def collection(self, name: str) -> _Coll:
        return _Coll(self.store, name)

    def batch(self) -> _Batch:
        return _Batch()


WORK_ID = "10.1000__mine"
WORK_PATH = f"users/u1/trackedWorks/{WORK_ID}"


def _work(**kw) -> TrackedWork:
    return TrackedWork(
        id=WORK_ID, doi="10.1000/mine", openalex_id="W1", title="My paper",
        last_checked_at=kw.pop("last_checked_at", _NOW - timedelta(days=1)), **kw,
    )


def _oa(title: str, *, doi: str | None, pub: str, wid: str = "W9", arxiv: str | None = None,
        type_: str = "article") -> dict:
    locations = [{"landing_page_url": f"https://arxiv.org/abs/{arxiv}"}] if arxiv else []
    return {
        "id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title, "publication_year": int(pub[:4]), "publication_date": pub,
        "authorships": [], "locations": locations, "type": type_,
    }


def _s2(title: str, *, doi: str | None, pub: str, pid: str = "p9", arxiv: str | None = None) -> dict:
    ext = {k: v for k, v in (("DOI", doi), ("ArXiv", arxiv)) if v}
    return {"paperId": pid, "externalIds": ext, "title": title,
            "year": int(pub[:4]), "publicationDate": pub, "authors": []}


async def _check(db: _DB, work: TrackedWork, oa: list, s2: list, **kw):
    with patch("citey.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("citey.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=s2)):
        return await process_tracked_work("u1", work, db, **kw)


LONG = "Calibrated uncertainty for tool using language model agents"


# ---------------------------------------------------------------------------
# Identity and junk
# ---------------------------------------------------------------------------


def test_preprint_and_journal_version_merge_through_arxiv_id() -> None:
    merged = merge_records([
        {"id": "S2:a", "doi": "10.48550/arxiv.2506.02005", "title": "Preprint title here, quite long"},
        {"id": "W5", "doi": "10.1103/physrevd.1", "arxiv_id": "2506.02005v2", "title": "Journal title"},
    ])
    assert len(merged) == 1
    assert merged[0]["doi"] == "10.48550/arxiv.2506.02005"


def test_record_without_doi_merges_by_title() -> None:
    merged = merge_records([
        {"id": "W5", "doi": "10.1/x", "title": LONG},
        {"id": "S2:b", "doi": None, "title": LONG.upper() + "."},
    ])
    assert len(merged) == 1 and "id:s2:b" in merged[0]["_keys"]


def test_short_generic_titles_never_merge_different_papers() -> None:
    assert title_key("Editorial") is None
    assert title_key("Reply to comment") is None
    merged = merge_records([{"id": "W1", "title": "Editorial"}, {"id": "W2", "title": "Editorial"}])
    assert len(merged) == 2


@pytest.mark.parametrize("title", [
    "Correction to: Deep learning for proteins", "Erratum: A study", "Retraction Note: Something",
    "Expression of Concern: X", "Publisher's Note: Y", "Corrigendum", "Retracted: Z",
])
def test_notices_are_junk(title: str) -> None:
    assert is_junk(title)


@pytest.mark.parametrize("title", [
    "Correction of lens aberrations in electron microscopy", "Retraction rates across fields",
    "Withdrawal symptoms in adolescents", "Errata in early printed books as historical evidence",
])
def test_research_titles_are_not_junk(title: str) -> None:
    assert not is_junk(title)


def test_openalex_erratum_type_is_junk() -> None:
    assert is_junk("Some title", "erratum")


# ---------------------------------------------------------------------------
# Late indexed citations and the quiet baseline
# ---------------------------------------------------------------------------


async def test_baseline_records_older_citations_without_alerting() -> None:
    db = _DB()
    db.store[WORK_PATH] = {}
    count, notes = await _check(db, _work(), [
        _oa("A recent citing paper with enough words", doi="10.1/new", pub=_day(3), wid="W2"),
        _oa("An older citing paper with enough words", doi="10.1/old", pub=_day(90), wid="W3"),
    ], [])
    assert count == 1 and notes[0].citing_work_doi == "10.1/new"
    stored = db.store[WORK_PATH]
    assert "doi:10.1/old" in stored["notified_keys"]
    assert stored["citation_window"] == _CITATION_WINDOW_VERSION


async def test_after_baseline_a_late_indexed_citation_is_reported() -> None:
    db = _DB()
    db.store[WORK_PATH] = {}
    count, notes = await _check(db, _work(), [
        _oa("Published two months ago but indexed this week", doi="10.1/late", pub=_day(60), wid="W4"),
    ], [], baseline_done=True)
    assert count == 1 and notes[0].citing_work_doi == "10.1/late"


async def test_baseline_not_marked_done_when_a_source_failed() -> None:
    from citey.services.source_errors import SourceUnavailable

    db = _DB()
    db.store[WORK_PATH] = {}
    with patch("citey.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=[])), \
         patch("citey.services.citation_service.s2_svc.get_citing_papers",
               new=AsyncMock(side_effect=SourceUnavailable("semantic_scholar", "429"))):
        await process_tracked_work("u1", _work(), db)
    assert "citation_window" not in db.store[WORK_PATH]


async def test_paper_gaining_a_doi_later_is_not_reported_twice() -> None:
    db = _DB()
    db.store[WORK_PATH] = {}
    first, _ = await _check(db, _work(), [], [_s2(LONG, doi=None, pub=_day(2), pid="abc")], baseline_done=True)
    keys = set(db.store[WORK_PATH]["notified_keys"])
    second, _ = await _check(
        db, _work(), [_oa(LONG, doi="10.1/now-has-doi", pub=_day(2), wid="W8")],
        [_s2(LONG, doi="10.1/now-has-doi", pub=_day(2), pid="abc")],
        baseline_done=True, notified_keys=keys,
    )
    assert (first, second) == (1, 0)


async def test_same_paper_from_both_sources_is_one_alert() -> None:
    db = _DB()
    db.store[WORK_PATH] = {}
    count, _ = await _check(
        db, _work(), [_oa(LONG, doi="10.1/both", pub=_day(2), wid="W7")],
        [_s2(LONG, doi=None, pub=_day(2), pid="zz")], baseline_done=True,
    )
    assert count == 1


async def test_errata_are_not_reported() -> None:
    db = _DB()
    db.store[WORK_PATH] = {}
    count, _ = await _check(db, _work(), [
        _oa("Correction to: My paper and its many words", doi="10.1/fix", pub=_day(2), wid="W6"),
    ], [], baseline_done=True)
    assert count == 0


# ---------------------------------------------------------------------------
# Alert emails are marked sent only after they are sent
# ---------------------------------------------------------------------------


def _user_db() -> _DB:
    db = _DB()
    db.store["users/u1"] = {"email": "r@example.com"}
    db.store[WORK_PATH] = {"doi": "10.1000/mine", "openalex_id": "W1", "title": "My paper",
                           "last_checked_at": _NOW - timedelta(days=1), "citation_window": _CITATION_WINDOW_VERSION}
    return db


async def _run(db: _DB, email_service) -> None:
    oa = [_oa("A brand new citing paper with enough words", doi="10.1/n", pub=_day(1), wid="W2")]
    with patch("citey.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("citey.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("citey.services.citation_service.openalex_svc.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("citey.services.semantic_scholar.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("citey.services.citation_service.firebase_auth.get_user") as get_user:
        get_user.return_value.email_verified = True
        await run_job_for_user("u1", db.store["users/u1"], db, email_service)


def _notifications(db: _DB) -> list[dict]:
    return [v for k, v in db.store.items() if k.startswith("users/u1/notifications/")]


async def test_failed_send_leaves_citation_pending_and_next_run_sends_it() -> None:
    db = _user_db()

    class Broken:
        send_digest_email = AsyncMock(side_effect=RuntimeError("domain not verified"))

    await _run(db, Broken)
    assert [n["emailed"] for n in _notifications(db)] == [False]

    class Working:
        send_digest_email = AsyncMock()

    await _run(db, Working)  # nothing new this time, but the pending one goes out
    Working.send_digest_email.assert_awaited_once()
    assert Working.send_digest_email.call_args.kwargs["total_citations"] == 1
    assert [n["emailed"] for n in _notifications(db)] == [True]


async def test_successful_send_marks_emailed_and_is_not_repeated() -> None:
    db = _user_db()

    class Working:
        send_digest_email = AsyncMock()

    await _run(db, Working)
    await _run(db, Working)
    assert Working.send_digest_email.await_count == 1
    assert [n["emailed"] for n in _notifications(db)] == [True]


def test_identity_keys_cover_every_identifier() -> None:
    keys = identity_keys(doi="10.48550/arXiv.1234.5678", title=LONG, source_ids=["S2:abc"])
    assert {"doi:10.48550/arxiv.1234.5678", "arxiv:1234.5678", "id:s2:abc"} <= keys
    assert any(k.startswith("title:") for k in keys)


# ACL Anthology papers: S2 often knows newer workshop papers only by DOI.

def test_acl_papers_are_looked_up_by_acl_id_and_doi():
    from citey.services.semantic_scholar import _candidate_ids

    assert _candidate_ids("10.18653/v1/2025.uncertainlp-main.23") == [
        "ACL:2025.uncertainlp-main.23",
        "DOI:10.18653/v1/2025.uncertainlp-main.23",
    ]


async def test_acl_count_comes_from_doi_when_acl_id_is_unknown():
    import respx
    from httpx import Response

    from citey.services.semantic_scholar import get_citation_counts

    with respx.mock:
        respx.post(url__regex=r".*/paper/batch.*").mock(
            return_value=Response(200, json=[None, {"paperId": "x", "citationCount": 8}])
        )
        counts = await get_citation_counts(["10.18653/v1/2025.uncertainlp-main.23"])
    assert counts == {"10.18653/v1/2025.uncertainlp-main.23": 8}


# A rate limit that asks for hours (a spent daily budget) must not stall the run.

@pytest.mark.parametrize("module", ["openalex", "semantic_scholar"])
async def test_long_retry_after_gives_up_instead_of_sleeping(module):
    import importlib

    import httpx
    import respx
    from httpx import Response

    svc = importlib.import_module(f"citey.services.{module}")
    sleep = AsyncMock()
    with respx.mock, patch.object(svc, "_sleep", sleep):
        respx.route().mock(return_value=Response(429, headers={"Retry-After": "78890"}))
        async with httpx.AsyncClient() as client:
            if module == "openalex":
                result = await svc._get_with_retry(client, "https://api.openalex.org/works", {})
            else:
                result = await svc._request_with_retry(
                    client, "GET", "https://api.semanticscholar.org/x", "t", throttle=False
                )
    assert result is None
    sleep.assert_not_awaited()

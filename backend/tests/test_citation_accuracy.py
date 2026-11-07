"""
Late indexed citations, duplicate and junk alerts, and reliable alert emails.

Each test pins one way the nightly check used to report the wrong thing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import CitingWork, Work
from app.services import alert_service, tracking_service
from app.services.account_service import Account
from app.services.citation_service import (
    _CITATION_WINDOW_VERSION,
    process_tracked_work,
    run_job_for_user,
)
from app.services.citing_identity import (
    identity_keys,
    is_junk,
    merge_records,
    title_key,
)
from app.store import CitationStore, UserStore, WorkStore
from sqlmodel import select

from tests.conftest import needs_db

_NOW = datetime.now(tz=timezone.utc)


def _day(days_ago: int) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# A tracked paper in the test database
# ---------------------------------------------------------------------------


WORK_KEY = "10.1000__mine"
# The name tests/test_user_resume.py imports; it is now the paper's key.
WORK_PATH = WORK_KEY


async def _work(session, *, uid: str = "u1", baseline_done: bool = False, **fields) -> Work:
    """*uid* (created if missing) tracks "My paper". Without *baseline_done*
    its first check is still the quiet baseline."""
    await UserStore(session).create(uid, email="r@example.com")
    work, _ = await tracking_service.track_paper(
        session, uid, WORK_KEY,
        {
            "doi": "10.1000/mine", "openalex_id": "W1", "title": "My paper",
            "last_checked_at": _NOW - timedelta(days=1),
            "citation_window": _CITATION_WINDOW_VERSION if baseline_done else None,
            **fields,
        },
        now=_NOW,
    )
    return work


async def _stored(session, work: Work) -> Work:
    """The paper's row as the database has it now."""
    return await WorkStore(session).refresh(work)


async def _known(session, work: Work) -> set[str]:
    return await CitationStore(session).known_keys(work.id)


async def _alerted(session, uid: str = "u1") -> list[str | None]:
    """DOIs of the citing papers *uid* was alerted about, newest first."""
    return [n.citing_work_doi for n in await alert_service.notifications(session, uid)]


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


async def _check(session, work: Work, oa: list, s2: list, **kw):
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=s2)):
        return await process_tracked_work(session, work, uid="u1", **kw)


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


@needs_db
async def test_baseline_records_older_citations_without_alerting(pg_session) -> None:
    """The first check announces only last month's citations, to every
    tracker; older ones are recorded as known and alert nobody."""
    work = await _work(pg_session)
    await _work(pg_session, uid="u2")
    count, notes = await _check(pg_session, work, [
        _oa("A recent citing paper with enough words", doi="10.1/new", pub=_day(3), wid="W2"),
        _oa("An older citing paper with enough words", doi="10.1/old", pub=_day(90), wid="W3"),
    ], [])
    assert count == 1 and notes[0].citing_work_doi == "10.1/new"
    assert "doi:10.1/old" in await _known(pg_session, work)
    assert await _alerted(pg_session, "u1") == await _alerted(pg_session, "u2") == ["10.1/new"]
    assert (await _stored(pg_session, work)).citation_window == _CITATION_WINDOW_VERSION


@needs_db
async def test_after_baseline_a_late_indexed_citation_is_reported(pg_session) -> None:
    """Once the baseline is done, a citation published two months ago but
    indexed only now is still news."""
    work = await _work(pg_session, baseline_done=True)
    count, notes = await _check(pg_session, work, [
        _oa("Published two months ago but indexed this week", doi="10.1/late", pub=_day(60), wid="W4"),
    ], [])
    assert count == 1 and notes[0].citing_work_doi == "10.1/late"
    assert await _alerted(pg_session) == ["10.1/late"]


@needs_db
async def test_baseline_not_marked_done_when_a_source_failed(pg_session) -> None:
    """A source that was down could return a year of citations tomorrow, so
    the baseline stays open."""
    from app.services.source_errors import SourceUnavailable

    work = await _work(pg_session)
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.s2_svc.get_citing_papers",
               new=AsyncMock(side_effect=SourceUnavailable("semantic_scholar", "429"))):
        await process_tracked_work(pg_session, work)
    assert (await _stored(pg_session, work)).citation_window is None


@needs_db
async def test_paper_gaining_a_doi_later_is_not_reported_twice(pg_session) -> None:
    """A paper first seen without a DOI is recognised by its S2 ID and title
    when it comes back with one."""
    work = await _work(pg_session, baseline_done=True)
    first, _ = await _check(pg_session, work, [], [_s2(LONG, doi=None, pub=_day(2), pid="abc")])
    second, _ = await _check(
        pg_session, work, [_oa(LONG, doi="10.1/now-has-doi", pub=_day(2), wid="W8")],
        [_s2(LONG, doi="10.1/now-has-doi", pub=_day(2), pid="abc")],
    )
    assert (first, second) == (1, 0)
    assert len(await _alerted(pg_session)) == 1


@needs_db
async def test_same_paper_from_both_sources_is_one_alert(pg_session) -> None:
    """OpenAlex with a DOI and S2 without one, same title: one citation."""
    work = await _work(pg_session, baseline_done=True)
    count, _ = await _check(
        pg_session, work, [_oa(LONG, doi="10.1/both", pub=_day(2), wid="W7")],
        [_s2(LONG, doi=None, pub=_day(2), pid="zz")],
    )
    assert count == 1
    assert await _alerted(pg_session) == ["10.1/both"]
    assert len((await pg_session.exec(select(CitingWork))).all()) == 1


@needs_db
async def test_errata_are_not_reported(pg_session) -> None:
    """A correction notice is not a citation: no alert, nothing recorded."""
    work = await _work(pg_session, baseline_done=True)
    count, _ = await _check(pg_session, work, [
        _oa("Correction to: My paper and its many words", doi="10.1/fix", pub=_day(2), wid="W6"),
    ], [])
    assert count == 0
    assert await _alerted(pg_session) == []
    assert await _known(pg_session, work) == set()


# ---------------------------------------------------------------------------
# Alert emails are marked sent only after they are sent
# ---------------------------------------------------------------------------


async def _user_db(session) -> Work:
    """u1 (with an email address) tracks "My paper", baseline done."""
    return await _work(session, baseline_done=True)


async def _run(session, email_service) -> None:
    oa = [_oa("A brand new citing paper with enough words", doi="10.1/n", pub=_day(1), wid="W2")]
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=oa)), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.openalex_svc.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("app.services.semantic_scholar.get_citation_counts", new=AsyncMock(return_value={})), \
         patch("app.services.account_service.get_account",
               new=AsyncMock(return_value=Account("u1", "ada@uni.edu", True, "firebase"))):
        await run_job_for_user("u1", session, email_service, settings=MagicMock())


async def _emailed(session) -> list[bool]:
    return [n.emailed for n in await alert_service.notifications(session, "u1")]


@needs_db
async def test_failed_send_leaves_citation_pending_and_next_run_sends_it(pg_session) -> None:
    """An alert whose email failed goes out with the next run."""
    await _user_db(pg_session)

    class Broken:
        send_digest_email = AsyncMock(side_effect=RuntimeError("domain not verified"))

    await _run(pg_session, Broken)
    assert await _emailed(pg_session) == [False]

    class Working:
        send_digest_email = AsyncMock()

    await _run(pg_session, Working)  # nothing new this time, but the pending one goes out
    Working.send_digest_email.assert_awaited_once()
    assert Working.send_digest_email.call_args.kwargs["total_citations"] == 1
    assert await _emailed(pg_session) == [True]


@needs_db
async def test_successful_send_marks_emailed_and_is_not_repeated(pg_session) -> None:
    """An alert that was emailed is not emailed again."""
    await _user_db(pg_session)

    class Working:
        send_digest_email = AsyncMock()

    await _run(pg_session, Working)
    await _run(pg_session, Working)
    assert Working.send_digest_email.await_count == 1
    assert await _emailed(pg_session) == [True]


def test_identity_keys_cover_every_identifier() -> None:
    keys = identity_keys(doi="10.48550/arXiv.1234.5678", title=LONG, source_ids=["S2:abc"])
    assert {"doi:10.48550/arxiv.1234.5678", "arxiv:1234.5678", "id:s2:abc"} <= keys
    assert any(k.startswith("title:") for k in keys)


# ACL Anthology papers: S2 often knows newer workshop papers only by DOI.

def test_acl_papers_are_looked_up_by_acl_id_and_doi():
    from app.services.semantic_scholar import _candidate_ids

    assert _candidate_ids("10.18653/v1/2025.uncertainlp-main.23") == [
        "ACL:2025.uncertainlp-main.23",
        "DOI:10.18653/v1/2025.uncertainlp-main.23",
    ]


async def test_acl_count_comes_from_doi_when_acl_id_is_unknown():
    import respx
    from app.services.semantic_scholar import get_citation_counts
    from httpx import Response

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

    svc = importlib.import_module(f"app.services.{module}")
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

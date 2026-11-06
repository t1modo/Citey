"""OpenCitations and Europe PMC as nightly citation sources."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from app.services import europe_pmc, opencitations
from app.services.source_errors import SourceUnavailable
from tests.test_citation_accuracy import LONG, WORK_PATH, _DB, _day, _oa, _work

from app.services.citation_service import _CITATION_WINDOW_VERSION, process_tracked_work

OTHER = "Measuring agreement between citation indexes across scholarly fields"
BIO = "Single cell imaging of mitochondrial calcium flux in cultured neurons"


async def _check(db, work, *, oa=(), oc=(), epmc=(), hydrate=(), crossref=None, **kw):
    hyd = AsyncMock(return_value=list(hydrate))
    cr = AsyncMock(return_value=crossref)
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=list(oa))), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.opencitations_svc.get_citing_refs", new=AsyncMock(return_value=list(oc))), \
         patch("app.services.citation_service.europe_pmc_svc.get_citing_works", new=AsyncMock(return_value=list(epmc))), \
         patch("app.services.citation_service.openalex_svc.get_works_by_ids", new=hyd), \
         patch("app.services.citation_service.crossref_svc.get_citing_metadata", new=cr):
        result = await process_tracked_work("u1", work, db, **kw)
    return result, hyd, cr


def _epmc(title: str, *, doi: str | None, pub: str, rid: str = "42") -> dict:
    return {
        "id": rid, "source": "MED", "doi": doi, "title": title + ".",
        "pubYear": pub[:4], "firstPublicationDate": pub,
        "authorList": {"author": [{
            "firstName": "Yang", "lastName": "Xu",
            "authorAffiliationDetailsList": {"authorAffiliation": [
                {"affiliation": "Department of Chemistry, Zhejiang University. y.xu@zju.edu.cn."}
            ]},
        }]},
        "pubTypeList": {"pubType": ["Journal Article"]},
    }


# ---------------------------------------------------------------------------
# Wiring into the nightly check
# ---------------------------------------------------------------------------


async def test_opencitations_only_citation_is_filled_in_from_openalex_and_reported() -> None:
    db = _DB()
    oc = [{"doi": "10.9/new", "openalex_id": "https://openalex.org/W77", "pmid": None,
           "publication_date": _day(3)}]
    (count, notes), hyd, cr = await _check(
        db, _work(), oc=oc, hydrate=[_oa(OTHER, doi="10.9/new", pub=_day(3), wid="W77")],
        baseline_done=True,
    )
    assert count == 1
    assert notes[0].citing_work_title == OTHER
    hyd.assert_awaited_once()
    assert hyd.await_args.kwargs["openalex_ids"] == ["https://openalex.org/W77"]
    cr.assert_not_awaited()


async def test_citations_openalex_already_returned_are_not_looked_up_again() -> None:
    db = _DB()
    oc = [{"doi": "10.9/a", "openalex_id": "https://openalex.org/W5", "pmid": None,
           "publication_date": _day(3)}]
    (count, _), hyd, _ = await _check(
        db, _work(), oa=[_oa(LONG, doi="10.9/a", pub=_day(3), wid="W5")], oc=oc, baseline_done=True,
    )
    assert count == 1
    hyd.assert_not_awaited()


async def test_crossref_fills_in_what_openalex_does_not_have() -> None:
    db = _DB()
    oc = [{"doi": "10.9/cr", "openalex_id": None, "pmid": None, "publication_date": _day(2)}]
    rec = {"id": "crossref:10.9/cr", "doi": "10.9/cr", "arxiv_id": None, "type": "journal-article",
           "title": OTHER, "authors": ["Ana Lee"], "affiliations": [], "year": int(_day(2)[:4]),
           "publication_date": _day(2), "url": "https://doi.org/10.9/cr"}
    (count, notes), hyd, cr = await _check(db, _work(), oc=oc, hydrate=[], crossref=rec, baseline_done=True)
    assert count == 1 and notes[0].citing_work_doi == "10.9/cr"
    assert hyd.await_args.kwargs["dois"] == ["10.9/cr"]
    cr.assert_awaited_once_with("10.9/cr")


async def test_retracted_paper_found_by_opencitations_is_not_reported() -> None:
    db = _DB()
    oc = [{"doi": "10.9/r", "openalex_id": "https://openalex.org/W8", "pmid": None,
           "publication_date": _day(2)}]
    retracted = {**_oa(OTHER, doi="10.9/r", pub=_day(2), wid="W8"), "is_retracted": True}
    (count, _), _, cr = await _check(db, _work(), oc=oc, hydrate=[retracted], baseline_done=True)
    assert count == 0
    cr.assert_not_awaited()


async def test_europe_pmc_citation_is_reported_with_openalex_metadata_when_available() -> None:
    db = _DB()
    oa_version = _oa(BIO, doi="10.9/bio", pub=_day(4), wid="W9")
    oa_version["authorships"] = [{"author": {"display_name": "Yang Xu"},
                                  "institutions": [{"display_name": "Zhejiang University"}]}]
    (count, notes), hyd, _ = await _check(
        db, _work(), epmc=[_epmc(BIO, doi="10.9/bio", pub=_day(4))], hydrate=[oa_version],
        baseline_done=True,
    )
    assert count == 1
    assert notes[0].citing_affiliations == ["Zhejiang University"]
    assert hyd.await_args.kwargs["dois"] == ["10.9/bio"]


async def test_europe_pmc_record_stands_alone_when_openalex_lacks_it() -> None:
    db = _DB()
    (count, notes), _, _ = await _check(
        db, _work(), epmc=[_epmc(BIO, doi=None, pub=_day(4))], baseline_done=True,
    )
    assert count == 1
    assert notes[0].citing_work_title == BIO
    assert notes[0].citing_authors == ["Yang Xu"]
    assert notes[0].citing_affiliations == ["Department of Chemistry, Zhejiang University"]
    assert notes[0].citing_work_url == "https://europepmc.org/article/MED/42"


async def test_same_paper_from_every_source_is_one_alert() -> None:
    db = _DB()
    oc = [{"doi": "10.9/a", "openalex_id": "https://openalex.org/W5", "pmid": None,
           "publication_date": _day(3)}]
    (count, _), _, _ = await _check(
        db, _work(), oa=[_oa(LONG, doi="10.9/a", pub=_day(3), wid="W5")], oc=oc,
        epmc=[_epmc(LONG, doi="10.9/A", pub=_day(3))], baseline_done=True,
    )
    assert count == 1


async def test_new_sources_start_with_a_quiet_baseline() -> None:
    db = _DB()
    oc = [{"doi": "10.9/old", "openalex_id": "https://openalex.org/W6", "pmid": None,
           "publication_date": _day(200)}]
    (count, _), _, _ = await _check(
        db, _work(), oc=oc, hydrate=[_oa(OTHER, doi="10.9/old", pub=_day(200), wid="W6")],
        baseline_done=False,
    )
    assert count == 0
    stored = db.store[WORK_PATH]
    assert "doi:10.9/old" in stored["notified_keys"]
    assert stored["citation_window"] == _CITATION_WINDOW_VERSION == 4


async def test_failed_lookup_keeps_the_baseline_open() -> None:
    db = _DB()
    oc = [{"doi": "10.9/x", "openalex_id": "https://openalex.org/W6", "pmid": None,
           "publication_date": _day(200)}]
    failures: list[str] = []
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.opencitations_svc.get_citing_refs", new=AsyncMock(return_value=oc)), \
         patch("app.services.citation_service.openalex_svc.get_works_by_ids",
               new=AsyncMock(side_effect=SourceUnavailable("openalex", "429"))):
        await process_tracked_work("u1", _work(), db, baseline_done=False, source_failures=failures)
    assert failures == ["opencitations"]
    assert "citation_window" not in db.store[WORK_PATH]


async def test_source_outage_is_a_failure_not_an_empty_list() -> None:
    db = _DB()
    failures: list[str] = []
    with patch("app.services.citation_service.openalex_svc.get_citing_works", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.s2_svc.get_citing_papers", new=AsyncMock(return_value=[])), \
         patch("app.services.citation_service.europe_pmc_svc.get_citing_works",
               new=AsyncMock(side_effect=SourceUnavailable("europe_pmc", "503"))):
        await process_tracked_work("u1", _work(), db, baseline_done=False, source_failures=failures)
    assert failures == ["europe_pmc"]
    assert "citation_window" not in db.store[WORK_PATH]


# ---------------------------------------------------------------------------
# The clients
# ---------------------------------------------------------------------------


@pytest.mark.real_extra_sources
async def test_opencitations_parses_ids_and_drops_old_citations() -> None:
    rows = [
        {"citing": "omid:br/1 openalex:W1 doi:10.1/New", "creation": "2026-10-31"},
        {"citing": "omid:br/2 doi:10.1/old", "creation": "2024-01-02"},
        {"citing": "omid:br/3 doi:10.1/month", "creation": "2026-10"},
        {"citing": "omid:br/4", "creation": "2026-10-01"},
        {"citing": "omid:br/1 openalex:W1 doi:10.1/new", "creation": "2026-10-31"},
    ]
    with respx.mock:
        route = respx.get(url__regex=r".*/citations/doi:10\.18653/v1/x").mock(return_value=Response(200, json=rows))
        refs = await opencitations.get_citing_refs("https://doi.org/10.18653/v1/X", since_date="2026-10-15")
    assert route.called
    assert refs == [
        {"doi": "10.1/new", "openalex_id": "https://openalex.org/W1", "pmid": None, "publication_date": "2026-10-31"},
        {"doi": "10.1/month", "openalex_id": None, "pmid": None, "publication_date": "2026-10"},
    ]


@pytest.mark.real_extra_sources
async def test_opencitations_outage_raises() -> None:
    with respx.mock:
        respx.get(url__regex=r".*opencitations.*").mock(return_value=Response(503))
        with pytest.raises(SourceUnavailable):
            await opencitations.get_citing_refs("10.1/x")


@pytest.mark.real_extra_sources
async def test_europe_pmc_looks_up_the_doi_then_its_citations() -> None:
    lookup = {"resultList": {"result": [
        {"id": "23903748", "source": "MED", "doi": "10.1038/NATURE12373"},
        {"id": "PPR1", "source": "PPR", "doi": "10.1038/nature12373"},
        {"id": "999", "source": "MED", "doi": "10.1038/other"},
    ]}}
    page = {"nextCursorMark": "abc", "resultList": {"result": [_epmc(BIO, doi="10.9/bio", pub="2026-10-19")]}}
    last = {"nextCursorMark": "abc", "resultList": {"result": []}}
    queries: list[str] = []

    def _respond(request):
        q = request.url.params["query"]
        queries.append(q)
        if q.startswith("DOI:"):
            return Response(200, json=lookup)
        return Response(200, json=page if request.url.params["cursorMark"] == "*" else last)

    with respx.mock:
        respx.get(url__regex=r".*europepmc.*").mock(side_effect=_respond)
        results = await europe_pmc.get_citing_works("10.1038/nature12373", since_date="2025-11-06")
    assert len(results) == 1
    assert queries[1] == "(CITES:23903748_MED OR CITES:PPR1_PPR) AND FIRST_PDATE:[2025-11-06 TO 3000-12-31]"


@pytest.mark.real_extra_sources
async def test_europe_pmc_skips_papers_it_does_not_index() -> None:
    with respx.mock:
        route = respx.get(url__regex=r".*europepmc.*").mock(
            return_value=Response(200, json={"hitCount": 0, "resultList": {"result": []}})
        )
        assert await europe_pmc.get_citing_works("10.18653/v1/x") == []
    assert route.call_count == 1


def test_europe_pmc_notices_are_marked_as_junk_types() -> None:
    raw = _epmc("Correction to an earlier study of neurons", doi=None, pub="2026-10-01")
    raw["pubTypeList"] = {"pubType": ["Published Erratum"]}
    assert europe_pmc.normalize_citing_work(raw)["type"] == "erratum"

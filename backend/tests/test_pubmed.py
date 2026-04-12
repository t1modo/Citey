"""
Tests for the PubMed service (app/services/pubmed.py).

Covers:
  1. search_authors — probe returns a candidate when PubMed has results,
     returns empty list when count is zero, and handles HTTP errors.
  2. get_works_by_author — normalizes summaries to OA-compatible dicts,
     skips papers without DOIs, handles esearch failures, and handles
     esummary failures gracefully.
  3. _normalize_work edge cases — year parsing, DOI prefix normalisation.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.services.pubmed import _normalize_work, get_works_by_author, search_authors

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _esearch_resp(count: int, ids: list[str]) -> dict:
    return {"esearchresult": {"count": str(count), "idlist": ids}}


def _esummary_resp(pmids: list[str], doi_prefix: str = "10.1234/test") -> dict:
    result: dict = {"uids": pmids}
    for pmid in pmids:
        result[pmid] = {
            "uid": pmid,
            "title": f"Paper {pmid}",
            "pubdate": "2024 Jan",
            "authors": [{"name": "Do T"}, {"name": "Smith J"}],
            "articleids": [
                {"idtype": "pubmed", "value": pmid},
                {"idtype": "doi", "value": f"{doi_prefix}.{pmid}"},
            ],
        }
    return {"result": result}


# ---------------------------------------------------------------------------
# 1. search_authors
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_authors_returns_candidate_when_results_exist() -> None:
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(7, ["99001"]))
    )
    result = await search_authors("Bio Author A")
    assert len(result) == 1
    assert result[0]["name"] == "Bio Author A"
    assert result[0]["authorId"] == "Bio Author A"
    assert result[0]["paperCount"] == 7


@respx.mock
async def test_search_authors_returns_empty_when_count_zero() -> None:
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(0, []))
    )
    result = await search_authors("Nonexistent Bio Author B")
    assert result == []


@respx.mock
async def test_search_authors_returns_empty_on_http_error() -> None:
    respx.get(url__regex=r".*/esearch.*").mock(return_value=Response(500))
    result = await search_authors("Error Bio Author C")
    assert result == []


# ---------------------------------------------------------------------------
# 2. get_works_by_author
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_works_by_author_normalizes_to_oa_format() -> None:
    pmids = ["55501", "55502"]
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(2, pmids))
    )
    respx.get(url__regex=r".*/esummary.*").mock(
        return_value=Response(200, json=_esummary_resp(pmids, doi_prefix="10.9999/bio"))
    )
    works = await get_works_by_author("Bio Works Author D")
    assert len(works) == 2
    dois = {w["doi"] for w in works}
    assert "https://doi.org/10.9999/bio.55501" in dois
    assert "https://doi.org/10.9999/bio.55502" in dois
    # Verify OA-compatible structure
    w = works[0]
    assert "title" in w
    assert "publication_year" in w
    assert "authorships" in w
    assert w["cited_by_count"] == 0
    assert w["id"].startswith("pubmed:")


@respx.mock
async def test_get_works_skips_papers_without_doi() -> None:
    pmids = ["66601"]
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(1, pmids))
    )
    # Summary has no doi entry in articleids
    no_doi_summary = {
        "result": {
            "66601": {
                "uid": "66601",
                "title": "No DOI Paper",
                "pubdate": "2023",
                "authors": [{"name": "Author X"}],
                "articleids": [{"idtype": "pubmed", "value": "66601"}],
            }
        }
    }
    respx.get(url__regex=r".*/esummary.*").mock(
        return_value=Response(200, json=no_doi_summary)
    )
    works = await get_works_by_author("No DOI Bio Author E")
    assert works == []


@respx.mock
async def test_get_works_returns_empty_when_esearch_fails() -> None:
    respx.get(url__regex=r".*/esearch.*").mock(return_value=Response(503))
    works = await get_works_by_author("Esearch Fail Author F")
    assert works == []


@respx.mock
async def test_get_works_returns_empty_when_no_pmids() -> None:
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(0, []))
    )
    works = await get_works_by_author("Zero Results Bio Author G")
    assert works == []


@respx.mock
async def test_get_works_handles_esummary_failure_gracefully() -> None:
    pmids = ["77701"]
    respx.get(url__regex=r".*/esearch.*").mock(
        return_value=Response(200, json=_esearch_resp(1, pmids))
    )
    respx.get(url__regex=r".*/esummary.*").mock(return_value=Response(429, headers={"Retry-After": "0"}))
    # All retries exhausted → should return empty list, not raise
    works = await get_works_by_author("Esummary Fail Author H")
    assert works == []


# ---------------------------------------------------------------------------
# 3. _normalize_work edge cases
# ---------------------------------------------------------------------------


def test_normalize_work_strips_trailing_period_from_title() -> None:
    summary = {
        "title": "A great paper.",
        "pubdate": "2021",
        "authors": [{"name": "Doe J"}],
        "articleids": [{"idtype": "doi", "value": "10.1111/great"}],
    }
    work = _normalize_work(summary, "88801")
    assert work is not None
    assert work["title"] == "A great paper"


def test_normalize_work_prefixes_bare_doi() -> None:
    summary = {
        "title": "Prefixed DOI Test",
        "pubdate": "2022",
        "authors": [],
        "articleids": [{"idtype": "doi", "value": "10.2222/prefix.test"}],
    }
    work = _normalize_work(summary, "88802")
    assert work is not None
    assert work["doi"] == "https://doi.org/10.2222/prefix.test"


def test_normalize_work_keeps_full_url_doi_unchanged() -> None:
    summary = {
        "title": "Full URL DOI Test",
        "pubdate": "2022",
        "authors": [],
        "articleids": [{"idtype": "doi", "value": "https://doi.org/10.3333/full"}],
    }
    work = _normalize_work(summary, "88803")
    assert work is not None
    assert work["doi"] == "https://doi.org/10.3333/full"


def test_normalize_work_returns_none_when_no_doi() -> None:
    summary = {
        "title": "No DOI",
        "pubdate": "2024",
        "authors": [],
        "articleids": [{"idtype": "pubmed", "value": "88804"}],
    }
    assert _normalize_work(summary, "88804") is None


def test_normalize_work_handles_non_numeric_year() -> None:
    summary = {
        "title": "Year Edge Case",
        "pubdate": "In Press",
        "authors": [],
        "articleids": [{"idtype": "doi", "value": "10.4444/year"}],
    }
    work = _normalize_work(summary, "88805")
    assert work is not None
    assert work["publication_year"] is None

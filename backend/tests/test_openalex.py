"""
Tests for app.services.openalex using respx to mock outbound HTTP calls.
"""

import re

import httpx
import pytest
import respx
from httpx import Response

from app.services.openalex import (
    _get_with_retry,
    extract_topics,
    extract_venue,
    get_citing_works,
    get_work_by_doi,
    normalize_citing_work,
)

_DOI = "10.1038/nature12345"
_RE_OA_WORKS = re.compile(r"https://api\.openalex\.org/works")

_RAW_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1038/nature12345",
    "title": "A Landmark Study in Genomics",
    "publication_year": 2021,
    "landing_page_url": "https://www.nature.com/articles/nature12345",
    "primary_topic": {"display_name": "Genomics"},
    "topics": [
        {"display_name": "Genomics"},
        {"display_name": "CRISPR"},
        {"display_name": "Molecular Biology"},
    ],
    "primary_location": {
        "source": {"display_name": "Nature"}
    },
    "authorships": [
        {
            "author": {"display_name": "Jane Smith"},
            "institutions": [
                {"display_name": "MIT"},
                {"display_name": "Broad Institute"},
            ],
        },
        {
            "author": {"display_name": "John Doe"},
            "institutions": [{"display_name": "Harvard University"}],
        },
    ],
}

_SAMPLE_RAW_CITING = {
    "id": "https://openalex.org/W9999999999",
    "doi": "https://doi.org/10.1016/j.cell.2022.01.001",
    "title": "A Follow-Up Study",
    "publication_year": 2022,
    "landing_page_url": "https://www.cell.com/cell/fulltext/S0092-8674(22)00001-0",
    "authorships": [
        {
            "author": {"display_name": "Alice Researcher"},
            "institutions": [{"display_name": "Stanford University"}],
        },
        {
            "author": {"display_name": "Bob Scientist"},
            "institutions": [],
        },
    ],
}


# ---------------------------------------------------------------------------
# get_work_by_doi (uses filter query param: ?filter=doi:...)
# ---------------------------------------------------------------------------


async def test_get_work_by_doi_found(respx_mock) -> None:
    """A successful OpenAlex lookup returns the raw work dict."""
    respx_mock.get(_RE_OA_WORKS).mock(
        return_value=Response(200, json={"results": [_RAW_WORK]})
    )

    result = await get_work_by_doi(_DOI)

    assert result is not None
    assert result["id"] == "https://openalex.org/W2741809807"
    assert result["title"] == "A Landmark Study in Genomics"


async def test_get_work_by_doi_found_strips_prefix(respx_mock) -> None:
    """Passing a full doi.org URL still resolves correctly."""
    respx_mock.get(_RE_OA_WORKS).mock(
        return_value=Response(200, json={"results": [_RAW_WORK]})
    )

    result = await get_work_by_doi(f"https://doi.org/{_DOI}")
    assert result is not None
    assert result["id"] == "https://openalex.org/W2741809807"


async def test_get_work_by_doi_not_found(respx_mock) -> None:
    """An empty results list returns None."""
    respx_mock.get(_RE_OA_WORKS).mock(
        return_value=Response(200, json={"results": []})
    )

    result = await get_work_by_doi(_DOI)
    assert result is None


async def test_get_work_by_doi_server_error_returns_none(respx_mock) -> None:
    """A 500 from OpenAlex returns None gracefully."""
    respx_mock.get(_RE_OA_WORKS).mock(return_value=Response(500))

    result = await get_work_by_doi(_DOI)
    assert result is None


async def test_get_work_by_doi_404_returns_none(respx_mock) -> None:
    """A 404 from OpenAlex returns None."""
    respx_mock.get(_RE_OA_WORKS).mock(return_value=Response(404))

    result = await get_work_by_doi(_DOI)
    assert result is None


# ---------------------------------------------------------------------------
# normalize_citing_work
# ---------------------------------------------------------------------------


def test_normalize_citing_work_full() -> None:
    normalized = normalize_citing_work(_SAMPLE_RAW_CITING)

    assert normalized["id"] == "https://openalex.org/W9999999999"
    assert normalized["doi"] == "10.1016/j.cell.2022.01.001"
    assert normalized["title"] == "A Follow-Up Study"
    assert normalized["year"] == 2022
    assert normalized["url"] == "https://doi.org/10.1016/j.cell.2022.01.001"
    assert "Alice Researcher" in normalized["authors"]
    assert "Bob Scientist" in normalized["authors"]
    assert "Stanford University" in normalized["affiliations"]


def test_normalize_citing_work_no_doi_uses_landing_page() -> None:
    raw = {**_SAMPLE_RAW_CITING, "doi": None}
    normalized = normalize_citing_work(raw)

    assert normalized["doi"] is None
    assert normalized["url"] == _SAMPLE_RAW_CITING["landing_page_url"]


def test_normalize_citing_work_deduplicates_affiliations() -> None:
    raw = {
        "id": "https://openalex.org/W111",
        "doi": None,
        "title": "Dedup Test",
        "publication_year": 2023,
        "landing_page_url": None,
        "authorships": [
            {"author": {"display_name": "Author One"}, "institutions": [{"display_name": "MIT"}]},
            {"author": {"display_name": "Author Two"}, "institutions": [{"display_name": "MIT"}]},
        ],
    }
    normalized = normalize_citing_work(raw)
    assert normalized["affiliations"].count("MIT") == 1


def test_normalize_citing_work_empty_authorships() -> None:
    raw = {
        "id": "https://openalex.org/W222",
        "doi": "https://doi.org/10.9999/test",
        "title": "Minimal Work",
        "publication_year": 2020,
        "landing_page_url": None,
        "authorships": [],
    }
    normalized = normalize_citing_work(raw)
    assert normalized["authors"] == []
    assert normalized["affiliations"] == []


def test_normalize_citing_work_no_year() -> None:
    raw = {**_SAMPLE_RAW_CITING, "publication_year": None}
    assert normalize_citing_work(raw)["year"] is None


def test_normalize_citing_work_doi_lowercased() -> None:
    """DOI in normalized output is always lowercase."""
    raw = {**_SAMPLE_RAW_CITING, "doi": "https://doi.org/10.1016/J.CELL.2022.01.001"}
    normalized = normalize_citing_work(raw)
    assert normalized["doi"] == normalized["doi"].lower()


def test_normalize_citing_work_no_doi_no_landing_page() -> None:
    """Works with neither doi nor landing_page_url have url=None."""
    raw = {**_SAMPLE_RAW_CITING, "doi": None, "landing_page_url": None}
    normalized = normalize_citing_work(raw)
    assert normalized["url"] is None


# ---------------------------------------------------------------------------
# extract_topics
# ---------------------------------------------------------------------------


def test_extract_topics_primary_first() -> None:
    assert extract_topics(_RAW_WORK)[0] == "Genomics"


def test_extract_topics_deduplicates() -> None:
    assert extract_topics(_RAW_WORK).count("Genomics") == 1


def test_extract_topics_max_three() -> None:
    assert len(extract_topics(_RAW_WORK)) <= 3


def test_extract_topics_no_topics() -> None:
    raw = {**_RAW_WORK, "primary_topic": None, "topics": []}
    assert extract_topics(raw) == []


def test_extract_topics_primary_only() -> None:
    raw = {**_RAW_WORK, "topics": []}
    topics = extract_topics(raw)
    assert topics == ["Genomics"]


# ---------------------------------------------------------------------------
# extract_venue
# ---------------------------------------------------------------------------


def test_extract_venue_returns_source_name() -> None:
    assert extract_venue(_RAW_WORK) == "Nature"


def test_extract_venue_no_location() -> None:
    assert extract_venue({**_RAW_WORK, "primary_location": None}) is None


def test_extract_venue_no_source() -> None:
    assert extract_venue({**_RAW_WORK, "primary_location": {"source": None}}) is None


def test_extract_venue_empty_name() -> None:
    raw = {**_RAW_WORK, "primary_location": {"source": {"display_name": ""}}}
    assert extract_venue(raw) is None


# ---------------------------------------------------------------------------
# _get_with_retry
# ---------------------------------------------------------------------------

_RE_ANY_OA = re.compile(r"https://api\.openalex\.org/.*")


async def test_get_with_retry_succeeds_immediately(respx_mock) -> None:
    """A 200 response is returned without any retry."""
    respx_mock.get(_RE_ANY_OA).mock(return_value=Response(200, json={"results": []}))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.openalex.org/works", {})
    assert resp is not None
    assert resp.status_code == 200


async def test_get_with_retry_retries_on_429(respx_mock) -> None:
    """A 429 then 200 succeeds after one retry (Retry-After: 0)."""
    respx_mock.get(_RE_ANY_OA).mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json={"results": []}),
        ]
    )
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.openalex.org/works", {})
    assert resp is not None
    assert resp.status_code == 200


async def test_get_with_retry_all_429_returns_none(respx_mock) -> None:
    """Exhausting all retries on 429 returns None."""
    respx_mock.get(_RE_ANY_OA).mock(
        return_value=Response(429, headers={"Retry-After": "0"})
    )
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(
            client, "https://api.openalex.org/works", {}, context="test"
        )
    assert resp is None


async def test_get_with_retry_network_error_returns_none(respx_mock) -> None:
    """A network error returns None without retrying."""
    respx_mock.get(_RE_ANY_OA).mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.openalex.org/works", {})
    assert resp is None


async def test_get_with_retry_500_returned_immediately(respx_mock) -> None:
    """Non-429 errors (500) are returned as-is without retry."""
    respx_mock.get(_RE_ANY_OA).mock(return_value=Response(500))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.openalex.org/works", {})
    assert resp is not None
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# get_citing_works — pagination
# ---------------------------------------------------------------------------


def _citing_work_stub(n: int) -> dict:
    return {
        "id": f"https://openalex.org/W{n:010d}",
        "doi": f"https://doi.org/10.9999/page{n}",
        "title": f"Citing Work {n}",
        "publication_year": 2024,
        "publication_date": "2026-03-01",
        "landing_page_url": None,
        "authorships": [],
    }


async def test_get_citing_works_single_page(respx_mock) -> None:
    """A response with no next_cursor stops after one page."""
    payload = {
        "results": [_citing_work_stub(1), _citing_work_stub(2)],
        "meta": {"next_cursor": None},
    }
    respx_mock.get(_RE_OA_WORKS).mock(return_value=Response(200, json=payload))

    results = await get_citing_works("W2741809807")
    assert len(results) == 2


async def test_get_citing_works_multiple_pages(respx_mock) -> None:
    """Cursor pagination collects results from all pages."""
    page1 = {
        "results": [_citing_work_stub(1)],
        "meta": {"next_cursor": "cursor_page2"},
    }
    page2 = {
        "results": [_citing_work_stub(2)],
        "meta": {"next_cursor": None},
    }
    respx_mock.get(_RE_OA_WORKS).mock(side_effect=[
        Response(200, json=page1),
        Response(200, json=page2),
    ])

    results = await get_citing_works("W2741809807")
    assert len(results) == 2
    titles = {r["title"] for r in results}
    assert "Citing Work 1" in titles
    assert "Citing Work 2" in titles


async def test_get_citing_works_429_mid_pagination_retries(respx_mock) -> None:
    """A 429 mid-pagination is retried and pagination resumes correctly."""
    page1 = {
        "results": [_citing_work_stub(1)],
        "meta": {"next_cursor": "cursor_page2"},
    }
    page2 = {
        "results": [_citing_work_stub(2)],
        "meta": {"next_cursor": None},
    }
    respx_mock.get(_RE_OA_WORKS).mock(side_effect=[
        Response(200, json=page1),
        Response(429, headers={"Retry-After": "0"}),  # 429 on page 2 request
        Response(200, json=page2),                     # retry succeeds
    ])

    results = await get_citing_works("W2741809807")
    assert len(results) == 2


async def test_get_citing_works_error_returns_partial(respx_mock) -> None:
    """A non-retryable error mid-pagination returns whatever was collected so far."""
    page1 = {
        "results": [_citing_work_stub(1)],
        "meta": {"next_cursor": "cursor_page2"},
    }
    respx_mock.get(_RE_OA_WORKS).mock(side_effect=[
        Response(200, json=page1),
        Response(500),  # hard error on page 2 — no retry
    ])

    results = await get_citing_works("W2741809807")
    # Only page 1 was collected before the error
    assert len(results) == 1
    assert results[0]["title"] == "Citing Work 1"


async def test_get_citing_works_empty_results(respx_mock) -> None:
    """An empty results page returns an empty list."""
    respx_mock.get(_RE_OA_WORKS).mock(
        return_value=Response(200, json={"results": [], "meta": {"next_cursor": None}})
    )
    results = await get_citing_works("W2741809807")
    assert results == []

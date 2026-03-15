"""
Tests for app.services.openalex using respx to mock outbound HTTP calls.
"""

import pytest
import respx
from httpx import Response

from app.services.openalex import get_work_by_doi, normalize_citing_work

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_DOI = "10.1038/nature12345"
_OPENALEX_WORK_URL = f"https://api.openalex.org/works/doi:{_DOI}"

_RAW_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1038/nature12345",
    "title": "A Landmark Study in Genomics",
    "publication_year": 2021,
    "landing_page_url": "https://www.nature.com/articles/nature12345",
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
            "institutions": [
                {"display_name": "Harvard University"},
            ],
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
            "institutions": [
                {"display_name": "Stanford University"},
            ],
        },
        {
            "author": {"display_name": "Bob Scientist"},
            "institutions": [],
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_work_by_doi_found() -> None:
    """A successful OpenAlex lookup should return the raw work dict."""
    respx.get(_OPENALEX_WORK_URL).mock(return_value=Response(200, json=_RAW_WORK))

    result = await get_work_by_doi(_DOI)

    assert result is not None
    assert result["id"] == "https://openalex.org/W2741809807"
    assert result["title"] == "A Landmark Study in Genomics"


@pytest.mark.asyncio
@respx.mock
async def test_get_work_by_doi_found_strips_prefix() -> None:
    """Passing a full doi.org URL should still resolve correctly."""
    respx.get(_OPENALEX_WORK_URL).mock(return_value=Response(200, json=_RAW_WORK))

    result = await get_work_by_doi(f"https://doi.org/{_DOI}")
    assert result is not None
    assert result["id"] == "https://openalex.org/W2741809807"


@pytest.mark.asyncio
@respx.mock
async def test_get_work_by_doi_not_found() -> None:
    """A 404 from OpenAlex should return None (not raise an exception)."""
    respx.get(_OPENALEX_WORK_URL).mock(return_value=Response(404))

    result = await get_work_by_doi(_DOI)
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_get_work_by_doi_server_error_returns_none() -> None:
    """A 500 from OpenAlex should return None gracefully."""
    respx.get(_OPENALEX_WORK_URL).mock(return_value=Response(500))

    result = await get_work_by_doi(_DOI)
    assert result is None


def test_normalize_citing_work_full() -> None:
    """normalize_citing_work should extract all expected fields correctly."""
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
    """When doi is absent, url should fall back to landing_page_url."""
    raw = {**_SAMPLE_RAW_CITING, "doi": None}
    normalized = normalize_citing_work(raw)

    assert normalized["doi"] is None
    assert normalized["url"] == _SAMPLE_RAW_CITING["landing_page_url"]


def test_normalize_citing_work_deduplicates_affiliations() -> None:
    """The same institution should not appear twice in affiliations."""
    raw = {
        "id": "https://openalex.org/W111",
        "doi": None,
        "title": "Dedup Test",
        "publication_year": 2023,
        "landing_page_url": None,
        "authorships": [
            {
                "author": {"display_name": "Author One"},
                "institutions": [{"display_name": "MIT"}],
            },
            {
                "author": {"display_name": "Author Two"},
                "institutions": [{"display_name": "MIT"}],  # duplicate
            },
        ],
    }
    normalized = normalize_citing_work(raw)
    assert normalized["affiliations"].count("MIT") == 1


def test_normalize_citing_work_empty_authorships() -> None:
    """Works with no authorships should return empty author and affiliation lists."""
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
    """Works with no publication_year should have year=None."""
    raw = {**_SAMPLE_RAW_CITING, "publication_year": None}
    normalized = normalize_citing_work(raw)
    assert normalized["year"] is None

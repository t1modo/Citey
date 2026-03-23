"""
Tests for app.services.crossref using respx to mock outbound HTTP calls.
"""

import re

import pytest
import respx
from fastapi import HTTPException
from httpx import Response

from app.services.crossref import resolve_doi

_SAMPLE_DOI = "10.1038/nature12345"

_CROSSREF_RESPONSE = {
    "status": "ok",
    "message-type": "work",
    "message": {
        "DOI": "10.1038/nature12345",
        "title": ["A Landmark Study in Genomics"],
        "author": [
            {"given": "Jane", "family": "Smith", "sequence": "first"},
            {"given": "John", "family": "Doe", "sequence": "additional"},
        ],
        "issued": {"date-parts": [[2021, 6, 15]]},
        "URL": "https://doi.org/10.1038/nature12345",
        "type": "journal-article",
    },
}

_RE_CROSSREF = re.compile(r"https://api\.crossref\.org/works/")
_RE_OPENALEX = re.compile(r"https://api\.openalex\.org/works")
_RE_DATACITE = re.compile(r"https://api\.datacite\.org/dois/")

# Empty fallback responses so Crossref-404 tests don't hit the network
_OA_EMPTY = Response(200, json={"results": []})
_DC_NOT_FOUND = Response(404)


async def test_resolve_doi_success(respx_mock) -> None:
    """A successful Crossref lookup returns normalized metadata."""
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=_CROSSREF_RESPONSE))

    result = await resolve_doi(_SAMPLE_DOI)

    assert result["doi"] == "10.1038/nature12345"
    assert result["title"] == "A Landmark Study in Genomics"
    assert result["authors"] == ["Jane Smith", "John Doe"]
    assert result["year"] == 2021
    assert result["url"] == "https://doi.org/10.1038/nature12345"
    assert result["openalex_id"] is None


async def test_resolve_doi_strips_https_prefix(respx_mock) -> None:
    """Passing a full https://doi.org/... URL resolves correctly."""
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=_CROSSREF_RESPONSE))

    result = await resolve_doi(f"https://doi.org/{_SAMPLE_DOI}")
    assert result["doi"] == "10.1038/nature12345"


async def test_resolve_doi_strips_doi_org_prefix(respx_mock) -> None:
    """doi.org/ prefix (without https://) is also stripped correctly."""
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=_CROSSREF_RESPONSE))

    result = await resolve_doi(f"doi.org/{_SAMPLE_DOI}")
    assert result["doi"] == "10.1038/nature12345"


async def test_resolve_doi_not_found_no_fallback(respx_mock) -> None:
    """404 from Crossref with no fallbacks raises HTTPException(404)."""
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(404))
    respx_mock.get(_RE_OPENALEX).mock(return_value=_OA_EMPTY)
    respx_mock.get(_RE_DATACITE).mock(return_value=_DC_NOT_FOUND)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_doi(_SAMPLE_DOI)

    assert exc_info.value.status_code == 404


async def test_resolve_doi_upstream_error(respx_mock) -> None:
    """A non-200/404 status from Crossref raises HTTPException(502)."""
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(500))

    with pytest.raises(HTTPException) as exc_info:
        await resolve_doi(_SAMPLE_DOI)

    assert exc_info.value.status_code == 502


async def test_resolve_doi_multi_part_title(respx_mock) -> None:
    """Crossref titles with multiple parts are joined with a space."""
    data = {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": _SAMPLE_DOI,
            "title": ["Part One", "Part Two"],
            "author": [],
            "issued": {"date-parts": [[2020]]},
            "URL": "https://doi.org/10.1038/nature12345",
        },
    }
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["title"] == "Part One Part Two"


async def test_resolve_doi_author_family_only(respx_mock) -> None:
    """Authors with only a family name have no leading space."""
    data = {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": _SAMPLE_DOI,
            "title": ["Some Title"],
            "author": [{"family": "Consortium", "sequence": "first"}],
            "issued": {"date-parts": [[2019]]},
            "URL": "https://doi.org/10.1038/nature12345",
        },
    }
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["authors"] == ["Consortium"]


async def test_resolve_doi_no_authors(respx_mock) -> None:
    """A work with no author field returns an empty authors list."""
    data = {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": _SAMPLE_DOI,
            "title": ["Authorless Work"],
            "issued": {"date-parts": [[2022]]},
            "URL": "https://doi.org/10.1038/nature12345",
        },
    }
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["authors"] == []


async def test_resolve_doi_no_year(respx_mock) -> None:
    """A work with no date fields returns year=None."""
    data = {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": _SAMPLE_DOI,
            "title": ["Dateless Work"],
            "author": [],
            "URL": "https://doi.org/10.1038/nature12345",
        },
    }
    respx_mock.get(_RE_CROSSREF).mock(return_value=Response(200, json=data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["year"] is None

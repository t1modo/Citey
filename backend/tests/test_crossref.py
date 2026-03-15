"""
Tests for app.services.crossref using respx to mock outbound HTTP calls.
"""

import pytest
import respx
from fastapi import HTTPException
from httpx import Response

from app.services.crossref import resolve_doi

# ---------------------------------------------------------------------------
# Sample Crossref API response (minimal but realistic)
# ---------------------------------------------------------------------------

_SAMPLE_DOI = "10.1038/nature12345"
_CROSSREF_URL = f"https://api.crossref.org/works/{_SAMPLE_DOI}"

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_success() -> None:
    """A successful Crossref lookup should return normalized metadata."""
    respx.get(_CROSSREF_URL).mock(
        return_value=Response(200, json=_CROSSREF_RESPONSE)
    )

    result = await resolve_doi(_SAMPLE_DOI)

    assert result["doi"] == "10.1038/nature12345"
    assert result["title"] == "A Landmark Study in Genomics"
    assert result["authors"] == ["Jane Smith", "John Doe"]
    assert result["year"] == 2021
    assert result["url"] == "https://doi.org/10.1038/nature12345"
    assert result["openalex_id"] is None


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_strips_https_prefix() -> None:
    """Passing a full https://doi.org/... URL should still resolve correctly."""
    respx.get(_CROSSREF_URL).mock(
        return_value=Response(200, json=_CROSSREF_RESPONSE)
    )

    result = await resolve_doi(f"https://doi.org/{_SAMPLE_DOI}")
    assert result["doi"] == "10.1038/nature12345"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_not_found() -> None:
    """A 404 from Crossref should raise HTTPException(404)."""
    respx.get(_CROSSREF_URL).mock(return_value=Response(404))

    with pytest.raises(HTTPException) as exc_info:
        await resolve_doi(_SAMPLE_DOI)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_upstream_error() -> None:
    """A non-200/404 status from Crossref should raise HTTPException(502)."""
    respx.get(_CROSSREF_URL).mock(return_value=Response(500))

    with pytest.raises(HTTPException) as exc_info:
        await resolve_doi(_SAMPLE_DOI)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_multi_part_title() -> None:
    """Crossref titles with multiple parts should be joined with a space."""
    response_data = {
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
    respx.get(_CROSSREF_URL).mock(return_value=Response(200, json=response_data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["title"] == "Part One Part Two"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_doi_author_family_only() -> None:
    """Authors with only a family name should not have a leading space."""
    response_data = {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": _SAMPLE_DOI,
            "title": ["Some Title"],
            "author": [
                {"family": "Consortium", "sequence": "first"},
            ],
            "issued": {"date-parts": [[2019]]},
            "URL": "https://doi.org/10.1038/nature12345",
        },
    }
    respx.get(_CROSSREF_URL).mock(return_value=Response(200, json=response_data))

    result = await resolve_doi(_SAMPLE_DOI)
    assert result["authors"] == ["Consortium"]

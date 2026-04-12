"""
Tests for the NASA ADS service (app/services/nasa_ads.py).

Covers:
  1. _first_last_to_ads / _ads_author_to_first_last — name-format conversions.
  2. search_authors — returns candidate when results exist, empty when count is
     zero, empty when token is absent, handles HTTP errors gracefully.
  3. get_works_by_author — normalizes ADS docs to OA-compatible format,
     skips documents without DOIs, handles pagination, handles HTTP errors.
  4. _normalize_work edge cases — DOI prefix, title list, year parsing,
     author list conversion.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import respx
from httpx import Response

from app.services.nasa_ads import (
    _ads_author_to_first_last,
    _first_last_to_ads,
    _normalize_work,
    get_works_by_author,
    search_authors,
)

_BASE = "https://api.adsabs.harvard.edu/v1/search/query"

# Fake token injected for all HTTP tests via the _get_token mock below.
_FAKE_TOKEN = "test-ads-token"


def _mock_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch _get_token so tests don't need a real ADS key in the env."""
    monkeypatch.setattr("app.services.nasa_ads._get_token", lambda: _FAKE_TOKEN)


# ---------------------------------------------------------------------------
# 1. Name format helpers
# ---------------------------------------------------------------------------


def test_first_last_to_ads_two_tokens() -> None:
    assert _first_last_to_ads("Timothy Do") == "Do, Timothy"


def test_first_last_to_ads_three_tokens() -> None:
    assert _first_last_to_ads("Timothy Khang Do") == "Do, Timothy Khang"


def test_first_last_to_ads_single_token() -> None:
    # Single token — return as-is
    assert _first_last_to_ads("Do") == "Do"


def test_ads_author_to_first_last_standard() -> None:
    assert _ads_author_to_first_last("Do, Timothy") == "Timothy Do"


def test_ads_author_to_first_last_with_middle() -> None:
    assert _ads_author_to_first_last("Do, Timothy Khang") == "Timothy Khang Do"


def test_ads_author_to_first_last_no_comma() -> None:
    # Already in "First Last" form — leave unchanged
    assert _ads_author_to_first_last("Timothy Do") == "Timothy Do"


def test_roundtrip_name_conversion() -> None:
    # "First Last" → ADS → back to "First Last" should be identity
    original = "Jane Smith"
    ads_form = _first_last_to_ads(original)
    assert _ads_author_to_first_last(ads_form) == original


# ---------------------------------------------------------------------------
# Helpers for building mock ADS responses
# ---------------------------------------------------------------------------


def _search_response(num_found: int, docs: list[dict]) -> dict:
    return {"response": {"numFound": num_found, "docs": docs}}


def _ads_doc(
    bibcode: str,
    title: str = "Test Paper",
    year: str = "2024",
    doi: str | None = "10.1234/ads.test",
    authors: list[str] | None = None,
    doctype: str = "article",
) -> dict:
    doc: dict = {
        "bibcode": bibcode,
        "title": [title],
        "year": year,
        "doctype": doctype,
        "author": authors or ["Do, Timothy", "Smith, Jane"],
    }
    if doi:
        doc["doi"] = [doi]
    return doc


# ---------------------------------------------------------------------------
# 2. search_authors
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_authors_returns_candidate_when_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    respx.get(url__regex=r".*search/query.*").mock(
        return_value=Response(200, json=_search_response(12, []))
    )
    result = await search_authors("ADS Author AA1")
    assert len(result) == 1
    assert result[0]["name"] == "ADS Author AA1"
    assert result[0]["paperCount"] == 12


@respx.mock
async def test_search_authors_returns_empty_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    respx.get(url__regex=r".*search/query.*").mock(
        return_value=Response(200, json=_search_response(0, []))
    )
    result = await search_authors("ADS Nonexistent Author BB2")
    assert result == []


async def test_search_authors_returns_empty_when_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.nasa_ads._get_token", lambda: "")
    result = await search_authors("ADS No Token Author CC3")
    assert result == []


@respx.mock
async def test_search_authors_returns_empty_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    respx.get(url__regex=r".*search/query.*").mock(return_value=Response(500))
    result = await search_authors("ADS HTTP Error Author DD4")
    assert result == []


# ---------------------------------------------------------------------------
# 3. get_works_by_author
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_works_normalizes_to_oa_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    docs = [
        _ads_doc("2024ApJ...001A", title="Astro Paper 1", doi="10.3847/1538-4357/aa001"),
        _ads_doc("2024ApJ...002B", title="Astro Paper 2", doi="10.3847/1538-4357/aa002"),
    ]
    respx.get(url__regex=r".*search/query.*").mock(
        return_value=Response(200, json=_search_response(2, docs))
    )
    works = await get_works_by_author("ADS Works Author EE5")
    assert len(works) == 2
    dois = {w["doi"] for w in works}
    assert "https://doi.org/10.3847/1538-4357/aa001" in dois
    assert "https://doi.org/10.3847/1538-4357/aa002" in dois
    # Verify OA-compatible structure
    w = works[0]
    assert "title" in w
    assert "publication_year" in w
    assert "authorships" in w
    assert w["cited_by_count"] == 0
    assert w["id"].startswith("ads:")


@respx.mock
async def test_get_works_skips_docs_without_doi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    no_doi_doc = _ads_doc("2024X..001", doi=None)
    respx.get(url__regex=r".*search/query.*").mock(
        return_value=Response(200, json=_search_response(1, [no_doi_doc]))
    )
    works = await get_works_by_author("ADS No DOI Author FF6")
    assert works == []


async def test_get_works_returns_empty_when_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.nasa_ads._get_token", lambda: "")
    works = await get_works_by_author("ADS No Token Works Author GG7")
    assert works == []


@respx.mock
async def test_get_works_returns_empty_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_token(monkeypatch)
    respx.get(url__regex=r".*search/query.*").mock(return_value=Response(503))
    works = await get_works_by_author("ADS HTTP Error Works Author HH8")
    assert works == []


@respx.mock
async def test_get_works_paginates_multiple_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two pages of 2 docs each; all 4 should be returned."""
    _mock_token(monkeypatch)
    page1 = [
        _ads_doc("2024X..P1A", doi="10.1111/p1a"),
        _ads_doc("2024X..P1B", doi="10.1111/p1b"),
    ]
    page2 = [
        _ads_doc("2024X..P2A", doi="10.1111/p2a"),
        _ads_doc("2024X..P2B", doi="10.1111/p2b"),
    ]
    # Return page1 first, then page2 for the second request.
    respx.get(url__regex=r".*search/query.*").mock(
        side_effect=[
            Response(200, json=_search_response(4, page1)),
            Response(200, json=_search_response(4, page2)),
        ]
    )
    # Temporarily lower _BATCH_SIZE to 2 to force pagination
    import app.services.nasa_ads as ads_mod
    original = ads_mod._BATCH_SIZE
    ads_mod._BATCH_SIZE = 2
    try:
        works = await get_works_by_author("ADS Paginated Author II9")
    finally:
        ads_mod._BATCH_SIZE = original
    assert len(works) == 4


# ---------------------------------------------------------------------------
# 4. _normalize_work edge cases
# ---------------------------------------------------------------------------


def test_normalize_work_prefixes_bare_doi() -> None:
    doc = _ads_doc("2024X..001", doi="10.9999/bare")
    work = _normalize_work(doc)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.9999/bare"


def test_normalize_work_keeps_full_url_doi_unchanged() -> None:
    doc = _ads_doc("2024X..002", doi="https://doi.org/10.9999/full")
    work = _normalize_work(doc)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.9999/full"


def test_normalize_work_returns_none_when_no_doi() -> None:
    doc = _ads_doc("2024X..003", doi=None)
    assert _normalize_work(doc) is None


def test_normalize_work_takes_first_title() -> None:
    doc = {"bibcode": "X", "title": ["First Title", "Second Title"], "year": "2024",
           "doi": ["10.1/t"], "author": [], "doctype": "article"}
    work = _normalize_work(doc)
    assert work is not None
    assert work["title"] == "First Title"


def test_normalize_work_handles_missing_title() -> None:
    doc = {"bibcode": "X", "title": [], "year": "2024",
           "doi": ["10.1/t"], "author": [], "doctype": "article"}
    work = _normalize_work(doc)
    assert work is not None
    assert work["title"] == ""


def test_normalize_work_converts_author_names() -> None:
    doc = _ads_doc("2024X..004", authors=["Do, Timothy", "Smith, Jane"])
    work = _normalize_work(doc)
    assert work is not None
    names = [a["author"]["display_name"] for a in work["authorships"]]
    assert "Timothy Do" in names
    assert "Jane Smith" in names


def test_normalize_work_handles_non_numeric_year() -> None:
    doc = _ads_doc("2024X..005", year="In Press")
    work = _normalize_work(doc)
    assert work is not None
    assert work["publication_year"] is None


def test_normalize_work_bibcode_in_id() -> None:
    doc = _ads_doc("2024ApJ...123T")
    work = _normalize_work(doc)
    assert work is not None
    assert work["id"] == "ads:2024ApJ...123T"

"""
Tests for the INSPIRE-HEP service (app/services/inspire_hep.py).

Covers:
  1. _inspire_to_first_last / _first_last_to_inspire — name-format conversions.
  2. search_authors — returns candidates with correct fields, handles HTTP
     errors, handles empty results.
  3. get_works_by_author — normalizes literature records to OA-compatible
     format, skips records without DOI or arXiv eprint, falls back to arXiv
     DOI when formal DOI is absent, handles pagination, handles HTTP errors.
  4. _normalize_work edge cases — DOI prefix, arXiv fallback, year parsing,
     author conversion, missing fields.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.services.inspire_hep import (
    _first_last_to_inspire,
    _inspire_to_first_last,
    _normalize_work,
    get_works_by_author,
    search_authors,
)

_AUTHORS_URL = "https://inspirehep.net/api/authors"
_LIT_URL = "https://inspirehep.net/api/literature"


# ---------------------------------------------------------------------------
# 1. Name format helpers
# ---------------------------------------------------------------------------


def test_inspire_to_first_last_standard() -> None:
    assert _inspire_to_first_last("Do, Timothy") == "Timothy Do"


def test_inspire_to_first_last_with_middle() -> None:
    assert _inspire_to_first_last("Do, Timothy Khang") == "Timothy Khang Do"


def test_inspire_to_first_last_no_comma() -> None:
    assert _inspire_to_first_last("Timothy Do") == "Timothy Do"


def test_inspire_to_first_last_strips_whitespace() -> None:
    assert _inspire_to_first_last("  Do,  Timothy  ") == "Timothy Do"


def test_first_last_to_inspire_two_tokens() -> None:
    assert _first_last_to_inspire("Timothy Do") == "Do, Timothy"


def test_first_last_to_inspire_three_tokens() -> None:
    assert _first_last_to_inspire("Timothy Khang Do") == "Do, Timothy Khang"


def test_first_last_to_inspire_single_token() -> None:
    assert _first_last_to_inspire("Do") == "Do"


def test_roundtrip_name_conversion() -> None:
    original = "Jane Smith"
    assert _inspire_to_first_last(_first_last_to_inspire(original)) == original


# ---------------------------------------------------------------------------
# Helpers for mock responses
# ---------------------------------------------------------------------------


def _authors_response(hits: list[dict]) -> dict:
    return {"hits": {"hits": hits, "total": len(hits)}}


def _lit_response(hits: list[dict], total: int | None = None) -> dict:
    return {"hits": {"hits": hits, "total": total if total is not None else len(hits)}}


def _author_hit(
    control_number: str,
    name: str = "Do, Timothy",
    paper_count: int = 5,
) -> dict:
    return {
        "id": control_number,
        "metadata": {
            "name": {"value": name},
            "stats": {"number_of_papers": paper_count},
        },
    }


def _lit_hit(
    record_id: str,
    title: str = "HEP Paper",
    doi: str | None = "10.18376/napac2025/mopa001",
    arxiv: str | None = None,
    authors: list[str] | None = None,
    date: str = "2025-01-01",
) -> dict:
    metadata: dict = {
        "titles": [{"title": title}],
        "earliest_date": date,
        "authors": [{"full_name": n} for n in (authors or ["Do, Timothy"])],
        "document_type": ["conference paper"],
    }
    if doi:
        metadata["dois"] = [{"value": doi}]
    if arxiv:
        metadata["arxiv_eprints"] = [{"value": arxiv}]
    return {"id": record_id, "metadata": metadata}


# ---------------------------------------------------------------------------
# 2. search_authors
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_authors_returns_candidates() -> None:
    respx.get(url__regex=r".*/authors.*").mock(
        return_value=Response(
            200,
            json=_authors_response([
                _author_hit("1111111", name="Do, Timothy", paper_count=8),
            ]),
        )
    )
    result = await search_authors("Inspire Author AA1")
    assert len(result) == 1
    assert result[0]["authorId"] == "1111111"
    # Name should be in First Last form for _names_match compatibility
    assert result[0]["name"] == "Timothy Do"
    assert result[0]["paperCount"] == 8


@respx.mock
async def test_search_authors_returns_empty_when_no_hits() -> None:
    respx.get(url__regex=r".*/authors.*").mock(
        return_value=Response(200, json=_authors_response([]))
    )
    result = await search_authors("Inspire Nonexistent Author BB2")
    assert result == []


@respx.mock
async def test_search_authors_returns_empty_on_http_error() -> None:
    respx.get(url__regex=r".*/authors.*").mock(return_value=Response(500))
    result = await search_authors("Inspire Error Author CC3")
    assert result == []


@respx.mock
async def test_search_authors_skips_hits_with_no_name() -> None:
    nameless = {"id": "9999999", "metadata": {"name": {}, "stats": {}}}
    respx.get(url__regex=r".*/authors.*").mock(
        return_value=Response(200, json=_authors_response([nameless]))
    )
    result = await search_authors("Inspire No Name Author DD4")
    assert result == []


# ---------------------------------------------------------------------------
# 3. get_works_by_author
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_works_normalizes_to_oa_format() -> None:
    hits = [
        _lit_hit("2222001", title="Paper A", doi="10.18376/napac2025/mopa001"),
        _lit_hit("2222002", title="Paper B", doi="10.18376/napac2025/mopa002"),
    ]
    respx.get(url__regex=r".*/literature.*").mock(
        return_value=Response(200, json=_lit_response(hits))
    )
    works = await get_works_by_author("Inspire Works Author EE5")
    assert len(works) == 2
    dois = {w["doi"] for w in works}
    assert "https://doi.org/10.18376/napac2025/mopa001" in dois
    assert "https://doi.org/10.18376/napac2025/mopa002" in dois
    w = works[0]
    assert "title" in w
    assert "publication_year" in w
    assert "authorships" in w
    assert w["cited_by_count"] == 0
    assert w["id"].startswith("inspire:")


@respx.mock
async def test_get_works_falls_back_to_arxiv_doi_when_no_doi() -> None:
    """Conference papers often lack a formal DOI but have an arXiv eprint."""
    hit = _lit_hit("3333001", doi=None, arxiv="2501.12345")
    respx.get(url__regex=r".*/literature.*").mock(
        return_value=Response(200, json=_lit_response([hit]))
    )
    works = await get_works_by_author("Inspire ArXiv Fallback Author FF6")
    assert len(works) == 1
    assert "arxiv" in works[0]["doi"].lower()


@respx.mock
async def test_get_works_skips_records_with_no_doi_or_arxiv() -> None:
    hit = _lit_hit("4444001", doi=None, arxiv=None)
    respx.get(url__regex=r".*/literature.*").mock(
        return_value=Response(200, json=_lit_response([hit]))
    )
    works = await get_works_by_author("Inspire Skip No ID Author GG7")
    assert works == []


@respx.mock
async def test_get_works_returns_empty_on_http_error() -> None:
    respx.get(url__regex=r".*/literature.*").mock(return_value=Response(503))
    works = await get_works_by_author("Inspire HTTP Error Author HH8")
    assert works == []


@respx.mock
async def test_get_works_paginates_multiple_pages() -> None:
    """With total=3 and page_size patched to 2, should fetch two pages."""
    page1 = [
        _lit_hit("5555001", doi="10.1/p1a"),
        _lit_hit("5555002", doi="10.1/p1b"),
    ]
    page2 = [
        _lit_hit("5555003", doi="10.1/p2a"),
    ]
    respx.get(url__regex=r".*/literature.*").mock(
        side_effect=[
            Response(200, json=_lit_response(page1, total=3)),
            Response(200, json=_lit_response(page2, total=3)),
        ]
    )
    import app.services.inspire_hep as inspire_mod
    original = inspire_mod._PAGE_SIZE
    inspire_mod._PAGE_SIZE = 2
    try:
        works = await get_works_by_author("Inspire Paginated Author II9")
    finally:
        inspire_mod._PAGE_SIZE = original
    assert len(works) == 3


# ---------------------------------------------------------------------------
# 4. _normalize_work edge cases
# ---------------------------------------------------------------------------


def test_normalize_work_prefixes_bare_doi() -> None:
    hit = _lit_hit("6001", doi="10.9999/bare")
    assert _normalize_work(hit) is not None
    assert _normalize_work(hit)["doi"] == "https://doi.org/10.9999/bare"  # type: ignore[index]


def test_normalize_work_keeps_full_url_doi() -> None:
    hit = _lit_hit("6002", doi="https://doi.org/10.9999/full")
    work = _normalize_work(hit)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.9999/full"


def test_normalize_work_arxiv_fallback_builds_correct_doi() -> None:
    hit = _lit_hit("6003", doi=None, arxiv="2501.99999")
    work = _normalize_work(hit)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.48550/arXiv.2501.99999"


def test_normalize_work_returns_none_when_no_doi_and_no_arxiv() -> None:
    hit = _lit_hit("6004", doi=None, arxiv=None)
    assert _normalize_work(hit) is None


def test_normalize_work_converts_author_names() -> None:
    hit = _lit_hit("6005", authors=["Do, Timothy", "Smith, Jane"])
    work = _normalize_work(hit)
    assert work is not None
    names = [a["author"]["display_name"] for a in work["authorships"]]
    assert "Timothy Do" in names
    assert "Jane Smith" in names


def test_normalize_work_parses_year_from_earliest_date() -> None:
    hit = _lit_hit("6006", date="2022-08-15")
    work = _normalize_work(hit)
    assert work is not None
    assert work["publication_year"] == 2022


def test_normalize_work_handles_missing_date() -> None:
    hit = _lit_hit("6007", date="")
    hit["metadata"].pop("imprint", None)
    work = _normalize_work(hit)
    assert work is not None
    assert work["publication_year"] is None


def test_normalize_work_takes_first_title() -> None:
    hit = _lit_hit("6008", title="First Title")
    hit["metadata"]["titles"] = [{"title": "First Title"}, {"title": "Second Title"}]
    work = _normalize_work(hit)
    assert work is not None
    assert work["title"] == "First Title"


def test_normalize_work_id_contains_record_id() -> None:
    hit = _lit_hit("7654321")
    work = _normalize_work(hit)
    assert work is not None
    assert work["id"] == "inspire:7654321"

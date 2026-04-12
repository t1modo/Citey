"""
Tests for the DBLP service (app/services/dblp.py).

Covers:
  1. _extract_pid — profile URL to PID conversion.
  2. _coerce_authors — single-dict vs list normalisation.
  3. search_authors — returns candidates with PID, handles empty results,
     handles single-hit dict response, handles HTTP errors.
  4. get_works_by_author — normalizes hits to OA-compatible dicts, skips
     hits without DOI, handles pagination, handles single-hit dict response,
     handles HTTP errors.
  5. _normalize_work edge cases — DOI prefix, title trailing period,
     year parsing, author coercion, missing fields.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.services.dblp import (
    _coerce_authors,
    _extract_pid,
    _normalize_work,
    get_works_by_author,
    search_authors,
)

_AUTHOR_URL = "https://dblp.org/search/author/api"
_PUBL_URL = "https://dblp.org/search/publ/api"


# ---------------------------------------------------------------------------
# 1. _extract_pid
# ---------------------------------------------------------------------------


def test_extract_pid_standard() -> None:
    assert _extract_pid("https://dblp.org/pid/12/3456") == "12/3456"


def test_extract_pid_letter_namespace() -> None:
    assert _extract_pid("https://dblp.org/pid/d/TimothyDo") == "d/TimothyDo"


def test_extract_pid_no_prefix_returned_as_is() -> None:
    assert _extract_pid("some/other/url") == "some/other/url"


# ---------------------------------------------------------------------------
# 2. _coerce_authors
# ---------------------------------------------------------------------------


def test_coerce_authors_list_returned_unchanged() -> None:
    authors = [{"text": "Alice"}, {"text": "Bob"}]
    assert _coerce_authors(authors) == authors


def test_coerce_authors_dict_wrapped_in_list() -> None:
    single = {"text": "Alice"}
    assert _coerce_authors(single) == [single]


def test_coerce_authors_none_returns_empty() -> None:
    assert _coerce_authors(None) == []


def test_coerce_authors_string_returns_empty() -> None:
    # Non-dict/list input should give empty list
    assert _coerce_authors("bad_input") == []


# ---------------------------------------------------------------------------
# Helpers for mock DBLP responses
# ---------------------------------------------------------------------------


def _author_response(hits: list[dict] | dict) -> dict:
    return {"result": {"hits": {"hit": hits, "@returned": str(len(hits) if isinstance(hits, list) else 1)}}}


def _publ_response(hits: list[dict] | dict, total: int | None = None) -> dict:
    hit_list = hits if isinstance(hits, list) else [hits]
    return {
        "result": {
            "hits": {
                "@total": str(total if total is not None else len(hit_list)),
                "hit": hits,
            }
        }
    }


def _author_hit(
    dblp_id: str,
    name: str = "Timothy Do",
    url: str = "https://dblp.org/pid/12/3456",
) -> dict:
    return {"@id": dblp_id, "info": {"author": name, "url": url}}


def _pub_hit(
    hit_id: str,
    title: str = "A CS Paper",
    doi: str | None = "10.1145/test.001",
    year: str = "2024",
    authors: list[str] | None = None,
    pub_type: str = "Conference and Workshop Papers",
) -> dict:
    info: dict = {
        "key": f"conf/test/{hit_id}",
        "title": title,
        "year": year,
        "type": pub_type,
        "authors": {
            "author": [{"@pid": f"xx/{i}", "text": n} for i, n in enumerate(authors or ["Do, Timothy"])]
        },
    }
    if doi:
        info["doi"] = doi
    return {"@id": hit_id, "info": info}


# ---------------------------------------------------------------------------
# 3. search_authors
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_authors_returns_candidates() -> None:
    respx.get(url__regex=r".*/author/api.*").mock(
        return_value=Response(
            200,
            json=_author_response([
                _author_hit("1", name="Timothy Do", url="https://dblp.org/pid/12/3456"),
            ]),
        )
    )
    result = await search_authors("DBLP Author AA1")
    assert len(result) == 1
    assert result[0]["name"] == "Timothy Do"
    assert result[0]["authorId"] == "12/3456"


@respx.mock
async def test_search_authors_handles_single_dict_hit() -> None:
    """DBLP returns a bare dict (not a list) when exactly one result matches."""
    respx.get(url__regex=r".*/author/api.*").mock(
        return_value=Response(
            200,
            json=_author_response(_author_hit("1", name="Solo Author")),
        )
    )
    result = await search_authors("DBLP Single Author BB2")
    assert len(result) == 1
    assert result[0]["name"] == "Solo Author"


@respx.mock
async def test_search_authors_returns_empty_when_no_hits() -> None:
    respx.get(url__regex=r".*/author/api.*").mock(
        return_value=Response(200, json=_author_response([]))
    )
    result = await search_authors("DBLP Nonexistent Author CC3")
    assert result == []


@respx.mock
async def test_search_authors_returns_empty_on_http_error() -> None:
    respx.get(url__regex=r".*/author/api.*").mock(return_value=Response(500))
    result = await search_authors("DBLP Error Author DD4")
    assert result == []


@respx.mock
async def test_search_authors_skips_hits_without_url() -> None:
    bad_hit = {"@id": "X", "info": {"author": "Ghost Author", "url": ""}}
    respx.get(url__regex=r".*/author/api.*").mock(
        return_value=Response(200, json=_author_response([bad_hit]))
    )
    result = await search_authors("DBLP Ghost Author EE5")
    assert result == []


# ---------------------------------------------------------------------------
# 4. get_works_by_author
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_works_normalizes_to_oa_format() -> None:
    hits = [
        _pub_hit("p1", title="Paper One", doi="10.1145/oa.001"),
        _pub_hit("p2", title="Paper Two", doi="10.1145/oa.002"),
    ]
    respx.get(url__regex=r".*/publ/api.*").mock(
        return_value=Response(200, json=_publ_response(hits))
    )
    works = await get_works_by_author("DBLP Works Pid FF6")
    assert len(works) == 2
    dois = {w["doi"] for w in works}
    assert "https://doi.org/10.1145/oa.001" in dois
    assert "https://doi.org/10.1145/oa.002" in dois
    w = works[0]
    assert "title" in w
    assert "publication_year" in w
    assert "authorships" in w
    assert w["cited_by_count"] == 0
    assert w["id"].startswith("dblp:")


@respx.mock
async def test_get_works_skips_hits_without_doi() -> None:
    hit = _pub_hit("p_no_doi", doi=None)
    respx.get(url__regex=r".*/publ/api.*").mock(
        return_value=Response(200, json=_publ_response([hit]))
    )
    works = await get_works_by_author("DBLP No DOI Pid GG7")
    assert works == []


@respx.mock
async def test_get_works_returns_empty_on_http_error() -> None:
    respx.get(url__regex=r".*/publ/api.*").mock(return_value=Response(503))
    works = await get_works_by_author("DBLP Error Pid HH8")
    assert works == []


@respx.mock
async def test_get_works_handles_single_dict_hit() -> None:
    """DBLP returns a bare dict when exactly one publication matches."""
    hit = _pub_hit("solo_p", doi="10.1145/solo.001")
    respx.get(url__regex=r".*/publ/api.*").mock(
        return_value=Response(200, json=_publ_response(hit, total=1))
    )
    works = await get_works_by_author("DBLP Single Pub Pid II9")
    assert len(works) == 1


@respx.mock
async def test_get_works_paginates_multiple_pages() -> None:
    """Three records across two pages (page_size patched to 2)."""
    page1 = [_pub_hit("pag1", doi="10.1/pg1a"), _pub_hit("pag2", doi="10.1/pg1b")]
    page2 = [_pub_hit("pag3", doi="10.1/pg2a")]

    respx.get(url__regex=r".*/publ/api.*").mock(
        side_effect=[
            Response(200, json=_publ_response(page1, total=3)),
            Response(200, json=_publ_response(page2, total=3)),
        ]
    )

    import app.services.dblp as dblp_mod
    original = dblp_mod._PAGE_SIZE
    dblp_mod._PAGE_SIZE = 2
    try:
        works = await get_works_by_author("DBLP Paginated Pid JJ10")
    finally:
        dblp_mod._PAGE_SIZE = original

    assert len(works) == 3


# ---------------------------------------------------------------------------
# 5. _normalize_work edge cases
# ---------------------------------------------------------------------------


def test_normalize_work_prefixes_bare_doi() -> None:
    hit = _pub_hit("n1", doi="10.1145/bare.001")
    work = _normalize_work(hit)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.1145/bare.001"


def test_normalize_work_keeps_full_url_doi() -> None:
    hit = _pub_hit("n2", doi="https://doi.org/10.1145/full.001")
    work = _normalize_work(hit)
    assert work is not None
    assert work["doi"] == "https://doi.org/10.1145/full.001"


def test_normalize_work_returns_none_when_no_doi() -> None:
    hit = _pub_hit("n3", doi=None)
    assert _normalize_work(hit) is None


def test_normalize_work_strips_trailing_period_from_title() -> None:
    hit = _pub_hit("n4", title="Attention Is All You Need.", doi="10.1/attn")
    work = _normalize_work(hit)
    assert work is not None
    assert work["title"] == "Attention Is All You Need"


def test_normalize_work_parses_year() -> None:
    hit = _pub_hit("n5", year="2019", doi="10.1/yr")
    work = _normalize_work(hit)
    assert work is not None
    assert work["publication_year"] == 2019


def test_normalize_work_handles_non_numeric_year() -> None:
    hit = _pub_hit("n6", year="TBD", doi="10.1/yr2")
    work = _normalize_work(hit)
    assert work is not None
    assert work["publication_year"] is None


def test_normalize_work_single_author_dict_coerced() -> None:
    """When DBLP returns a single author as a dict, not a list."""
    hit = _pub_hit("n7", doi="10.1/sa")
    hit["info"]["authors"]["author"] = {"@pid": "xx/1", "text": "Solo Author"}
    work = _normalize_work(hit)
    assert work is not None
    assert len(work["authorships"]) == 1
    assert work["authorships"][0]["author"]["display_name"] == "Solo Author"


def test_normalize_work_id_contains_dblp_key() -> None:
    hit = _pub_hit("conf_key", doi="10.1/id")
    work = _normalize_work(hit)
    assert work is not None
    assert "conf/test/conf_key" in work["id"]

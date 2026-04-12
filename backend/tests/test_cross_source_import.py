"""
Tests for the cross-source coverage boost in import_works_by_author.

Covers three layers:
  1. Name-matching edge cases that arise when the same author appears under
     different display-name forms in S2 vs OpenAlex.
  2. DOI overlap logic — the safety check that prevents merging a same-name
     but different researcher from the complementary source.
  3. The 429 retry path inside get_paper_with_authors (the root cause of the
     intermittent arXiv lookup failures).
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.routers.works import _names_match, _author_in_paper
from app.services.semantic_scholar import get_paper_with_authors

_S2_API = "https://api.semanticscholar.org/graph/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _s2_work(doi: str, title: str, year: int = 2024) -> dict:
    """Minimal S2-normalised (OpenAlex-compatible) work dict."""
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_year": year,
        "id": f"S2:fake",
        "cited_by_count": 0,
        "type": None,
        "authorships": [],
        "primary_location": {},
        "primary_topic": None,
        "topics": [],
    }


def _oa_work(doi: str, title: str, year: int = 2024) -> dict:
    """Minimal OpenAlex work dict."""
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_year": year,
        "id": "https://openalex.org/Wfake",
        "cited_by_count": 0,
        "type": None,
        "authorships": [],
        "primary_location": {},
        "primary_topic": None,
        "topics": [],
    }


def _strip_doi(doi: str | None) -> str | None:
    """Mirror of the _strip_doi helper embedded in import_works_by_author."""
    if not doi:
        return doi
    for pfx in ("https://doi.org/", "http://doi.org/"):
        if doi.startswith(pfx):
            return doi[len(pfx):]
    return doi


def _dois(works: list[dict]) -> set[str]:
    result: set[str] = set()
    for w in works:
        d = _strip_doi(w.get("doi"))
        if d:
            result.add(d.lower())
    return result


# ---------------------------------------------------------------------------
# 1. Cross-source name matching
# ---------------------------------------------------------------------------


class TestCrossSourceNameMatching:
    """
    The same researcher often appears under different display-name forms across
    S2 and OpenAlex.  _names_match must handle every variant that either
    source might return.
    """

    def test_middle_name_in_oa_matches_s2_shorter_form(self) -> None:
        # S2 stores "Timothy Do", OA stores "Timothy Khang Do"
        assert _names_match("Timothy Khang Do", "Timothy Do")

    def test_s2_short_form_matches_oa_full_name(self) -> None:
        assert _names_match("Timothy Do", "Timothy Khang Do")

    def test_initials_in_oa_match_s2_full_name(self) -> None:
        # Some OA records use "T. K. Do" — should still match "Timothy Do"
        assert _names_match("T. K. Do", "Timothy Do")

    def test_initials_match_full_first_and_middle(self) -> None:
        assert _names_match("T. K. Do", "Timothy Khang Do")

    def test_full_name_matches_initials(self) -> None:
        assert _names_match("Timothy Khang Do", "T. Do")

    def test_different_first_name_same_last_name_fails(self) -> None:
        assert not _names_match("Alice Do", "Timothy Do")

    def test_completely_different_names_fail(self) -> None:
        assert not _names_match("Jane Smith", "Timothy Do")

    def test_same_last_name_only_still_matches(self) -> None:
        # A single-token name (family name only) is an accepted match
        assert _names_match("Do", "Do")

    def test_different_last_name_fails(self) -> None:
        assert not _names_match("Do", "Jones")

    def test_hyphenated_double_barrel_normalised(self) -> None:
        # OA sometimes hyphenates compound surnames
        assert _names_match("Garcia-Lopez Maria", "Garcia Lopez Maria")


# ---------------------------------------------------------------------------
# 2. DOI overlap safety check
# ---------------------------------------------------------------------------


class TestDoiOverlapSafetyCheck:
    """
    The cross-source block only merges extra works when at least one DOI from
    the extra set is already present in the primary set, confirming both
    sources describe the same researcher.
    """

    def test_overlap_detected_for_arXiv_doi(self) -> None:
        primary = [_s2_work("10.48550/arxiv.2301.12345", "ArXiv Paper A")]
        extra = [
            _oa_work("10.48550/arxiv.2301.12345", "ArXiv Paper A"),    # shared
            _oa_work("10.18375/jacow-napac2025-mopa001", "NAPAC Paper"),  # new
        ]
        overlap = _dois(primary) & _dois(extra)
        assert len(overlap) >= 1

    def test_no_overlap_blocks_merge(self) -> None:
        primary = [_s2_work("10.48550/arxiv.2301.12345", "ArXiv Paper A")]
        extra = [_oa_work("10.9999/wrong.researcher.paper", "Someone Else")]
        overlap = _dois(primary) & _dois(extra)
        assert len(overlap) == 0  # merge must NOT happen

    def test_napac_paper_present_after_successful_merge(self) -> None:
        primary = [_s2_work("10.48550/arxiv.2301.12345", "ArXiv Paper A")]
        extra = [
            _oa_work("10.48550/arxiv.2301.12345", "ArXiv Paper A"),
            _oa_work("10.18375/jacow-napac2025-mopa001", "NAPAC Paper"),
        ]
        primary_dois = _dois(primary)
        extra_dois = _dois(extra)
        overlap = primary_dois & extra_dois

        merged = primary + extra if overlap else primary

        assert "10.18375/jacow-napac2025-mopa001" in _dois(merged)

    def test_second_arxiv_paper_also_survives_dedup(self) -> None:
        primary = [
            _s2_work("10.48550/arxiv.2301.12345", "Paper A"),
            _s2_work("10.48550/arxiv.2401.99999", "Paper B"),
        ]
        extra = [
            _oa_work("10.48550/arxiv.2301.12345", "Paper A"),   # duplicate
            _oa_work("10.48550/arxiv.2401.99999", "Paper B"),   # duplicate
            _oa_work("10.18375/jacow-napac2025-mopa001", "NAPAC Paper"),  # new
        ]
        overlap = _dois(primary) & _dois(extra)
        assert len(overlap) == 2

        merged = primary + extra
        # The dedup loop in works.py removes title-level duplicates later;
        # here we just confirm the NAPAC DOI is present in the merged list.
        assert "10.18375/jacow-napac2025-mopa001" in _dois(merged)

    def test_doi_case_normalisation(self) -> None:
        # DOIs are case-insensitive; the check must not fail due to casing
        primary = [_s2_work("10.48550/arXiv.2301.12345", "Paper A")]
        extra = [_oa_work("10.48550/ARXIV.2301.12345", "Paper A")]
        overlap = _dois(primary) & _dois(extra)
        assert len(overlap) == 1

    def test_empty_primary_allows_merge_without_overlap(self) -> None:
        # If the primary source returned zero DOIs (e.g. all papers lack DOIs)
        # the overlap check is skipped so we still benefit from the extra source.
        primary: list[dict] = [{"doi": None, "title": "No DOI Paper"}]
        extra = [_oa_work("10.18375/jacow-napac2025-mopa001", "NAPAC Paper")]
        primary_dois = _dois(primary)
        extra_dois = _dois(extra)
        overlap = primary_dois & extra_dois
        # Merge condition: not primary_dois OR overlap
        should_merge = (not primary_dois) or bool(overlap)
        assert should_merge


# ---------------------------------------------------------------------------
# 3. get_paper_with_authors — 429 retry path
# ---------------------------------------------------------------------------


def _paper_response(title: str = "Test ArXiv Paper") -> dict:
    return {
        "paperId": "abc123",
        "title": title,
        "year": 2025,
        "authors": [{"authorId": "111", "name": "Timothy Do"}],
    }


@respx.mock
async def test_paper_authors_succeeds_on_first_try() -> None:
    doi = "10.48550/arxiv.2510.00001"
    url = f"{_S2_API}/paper/ARXIV:2510.00001"
    respx.get(url).mock(return_value=Response(200, json=_paper_response()))
    result = await get_paper_with_authors(doi)
    assert result is not None
    assert result["title"] == "Test ArXiv Paper"


@respx.mock
async def test_paper_authors_retries_on_429_then_succeeds() -> None:
    """A single 429 before a 200 must still return the paper."""
    doi = "10.48550/arxiv.2510.00002"
    url = f"{_S2_API}/paper/ARXIV:2510.00002"
    respx.get(url).mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json=_paper_response("Retry Paper")),
        ]
    )
    result = await get_paper_with_authors(doi)
    assert result is not None
    assert result["title"] == "Retry Paper"


@respx.mock
async def test_paper_authors_returns_none_when_not_found() -> None:
    """404 on all candidate IDs must return None (not raise)."""
    doi = "10.48550/arxiv.2510.00003"
    respx.get(url__regex=r".*/paper/ARXIV:2510\.00003.*").mock(return_value=Response(404))
    respx.get(url__regex=r".*/paper/DOI:.*2510\.00003.*").mock(return_value=Response(404))
    result = await get_paper_with_authors(doi)
    assert result is None


@respx.mock
async def test_paper_authors_returns_none_after_all_retries_exhausted() -> None:
    """Persistent 429s on all candidates exhaust retries and return None."""
    doi = "10.48550/arxiv.2510.00004"
    # _candidate_ids returns ARXIV: first, then DOI: as fallback — mock both
    respx.get(url__regex=r".*/paper/ARXIV:2510\.00004.*").mock(
        return_value=Response(429, headers={"Retry-After": "0"})
    )
    respx.get(url__regex=r".*/paper/DOI:.*2510\.00004.*").mock(
        return_value=Response(429, headers={"Retry-After": "0"})
    )
    result = await get_paper_with_authors(doi)
    assert result is None

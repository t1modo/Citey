"""
Tests for app.services.semantic_scholar.

Covers:
  - normalize_citing_work       (completely untested until now)
  - _normalize_affiliation      (completely untested until now)
  - _match_canonical            (word-boundary correctness)
  - _get_with_retry             (429 retry logic, newly added)
"""

from __future__ import annotations

import re

import httpx
import pytest
import respx
from httpx import Response

from app.services.semantic_scholar import (
    _match_canonical,
    _normalize_affiliation,
    _get_with_retry,
    _resolve_s2_paper_id,
    get_citation_counts,
    get_citing_papers,
    normalize_citing_work,
)
from app.services.source_errors import SourceUnavailable

_RECENT_DATE = "2026-03-01"
_RE_S2 = re.compile(r"https://api\.semanticscholar\.org/.*")

# ---------------------------------------------------------------------------
# Shared test fixture
# ---------------------------------------------------------------------------

_FULL_S2_PAPER: dict = {
    "paperId": "abc123def456",
    "externalIds": {"DOI": "10.1234/s2test"},
    "title": "A Semantic Scholar Citing Work",
    "year": 2024,
    "publicationDate": _RECENT_DATE,
    "url": "https://www.semanticscholar.org/paper/abc123def456",
    "authors": [
        {
            "authorId": "1",
            "name": "Alice Researcher",
            "affiliations": ["Massachusetts Institute of Technology"],
        },
        {
            "authorId": "2",
            "name": "Bob Scientist",
            "affiliations": ["Stanford University"],
        },
    ],
}


# ---------------------------------------------------------------------------
# normalize_citing_work
# ---------------------------------------------------------------------------


class TestNormalizeCitingWork:
    def test_full_normalization(self) -> None:
        result = normalize_citing_work(_FULL_S2_PAPER)
        assert result["id"] == "S2:abc123def456"
        assert result["doi"] == "10.1234/s2test"
        assert result["title"] == "A Semantic Scholar Citing Work"
        assert result["year"] == 2024
        assert result["publication_date"] == _RECENT_DATE
        assert "Alice Researcher" in result["authors"]
        assert "Bob Scientist" in result["authors"]
        assert result["url"] == "https://doi.org/10.1234/s2test"

    def test_no_doi_uses_url_field(self) -> None:
        raw = {**_FULL_S2_PAPER, "externalIds": {}, "url": "https://s2.org/paper/abc"}
        result = normalize_citing_work(raw)
        assert result["doi"] is None
        assert result["url"] == "https://s2.org/paper/abc"

    def test_no_doi_no_url_field_uses_s2_paper_url(self) -> None:
        raw = {**_FULL_S2_PAPER, "externalIds": {}, "url": None}
        result = normalize_citing_work(raw)
        assert result["url"] == "https://www.semanticscholar.org/paper/abc123def456"

    def test_no_doi_no_url_no_paperid_returns_empty_url(self) -> None:
        raw = {**_FULL_S2_PAPER, "paperId": "", "externalIds": {}, "url": None}
        result = normalize_citing_work(raw)
        assert result["url"] == ""

    def test_empty_authors_produces_empty_lists(self) -> None:
        raw = {**_FULL_S2_PAPER, "authors": []}
        result = normalize_citing_work(raw)
        assert result["authors"] == []
        assert result["affiliations"] == []

    def test_author_with_no_name_excluded(self) -> None:
        """Authors whose name is empty/None must not appear in the authors list."""
        raw = {**_FULL_S2_PAPER, "authors": [{"authorId": "3", "name": "", "affiliations": []}]}
        result = normalize_citing_work(raw)
        assert result["authors"] == []

    def test_author_with_none_name_excluded(self) -> None:
        raw = {**_FULL_S2_PAPER, "authors": [{"authorId": "4", "name": None, "affiliations": []}]}
        result = normalize_citing_work(raw)
        assert result["authors"] == []

    def test_doi_prefix_stripped(self) -> None:
        raw = {**_FULL_S2_PAPER, "externalIds": {"DOI": "https://doi.org/10.1234/s2test"}}
        result = normalize_citing_work(raw)
        assert result["doi"] == "10.1234/s2test"

    def test_doi_http_prefix_stripped(self) -> None:
        raw = {**_FULL_S2_PAPER, "externalIds": {"DOI": "http://doi.org/10.1234/s2test"}}
        result = normalize_citing_work(raw)
        assert result["doi"] == "10.1234/s2test"

    def test_duplicate_affiliations_deduplicated(self) -> None:
        # Use the full canonical name — bare "MIT" is not in the canonical map;
        # _normalize_affiliation("Massachusetts Institute of Technology") → "MIT"
        raw = {
            **_FULL_S2_PAPER,
            "authors": [
                {"authorId": "1", "name": "Alice", "affiliations": ["Massachusetts Institute of Technology"]},
                {"authorId": "2", "name": "Bob", "affiliations": ["Massachusetts Institute of Technology"]},
            ],
        }
        result = normalize_citing_work(raw)
        assert result["affiliations"].count("MIT") == 1

    def test_missing_publication_date_is_none(self) -> None:
        raw = {**_FULL_S2_PAPER, "publicationDate": None}
        assert normalize_citing_work(raw)["publication_date"] is None

    def test_untitled_work_falls_back_to_untitled(self) -> None:
        raw = {**_FULL_S2_PAPER, "title": None}
        assert normalize_citing_work(raw)["title"] == "Untitled"

    def test_no_paper_id_produces_empty_s2_id(self) -> None:
        raw = {**_FULL_S2_PAPER, "paperId": None}
        result = normalize_citing_work(raw)
        assert result["id"] == ""

    def test_pdf_affiliations_used_when_s2_has_none(self) -> None:
        """_pdf_affiliations injected by enrichment step are used as fallback."""
        raw = {
            **_FULL_S2_PAPER,
            "authors": [{"authorId": "1", "name": "Alice", "affiliations": []}],
            "_pdf_affiliations": ["Dartmouth College"],
        }
        result = normalize_citing_work(raw)
        assert len(result["affiliations"]) > 0


# ---------------------------------------------------------------------------
# _normalize_affiliation
# ---------------------------------------------------------------------------


class TestNormalizeAffiliation:
    def test_mit_full_name(self) -> None:
        assert _normalize_affiliation("Massachusetts Institute of Technology") == "MIT"

    def test_stanford_with_geo_noise(self) -> None:
        assert _normalize_affiliation("Stanford University, CA, USA") == "Stanford"

    def test_google_research_before_broad_google(self) -> None:
        result = _normalize_affiliation("Google Research, Mountain View, CA")
        assert result == "Google Research"

    def test_microsoft_with_city_and_country(self) -> None:
        result = _normalize_affiliation("Microsoft, Beijing, China")
        assert result == "Microsoft"

    def test_empty_string_returns_none(self) -> None:
        assert _normalize_affiliation("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _normalize_affiliation("   ") is None

    def test_pure_geographic_returns_none(self) -> None:
        # Only country/city — no org keyword → should return None
        assert _normalize_affiliation("Beijing, China") is None

    def test_unknown_university_returns_none(self) -> None:
        # Unrecognised institutions return None so the UI shows "Independent"
        # rather than surfacing an unverified raw string as an affiliation pill.
        assert _normalize_affiliation("University of Somewhere Special") is None

    def test_carnegie_mellon_canonicalized(self) -> None:
        assert _normalize_affiliation("Carnegie Mellon University") == "CMU"

    def test_oxford_canonicalized(self) -> None:
        assert _normalize_affiliation("University of Oxford, UK") == "Oxford"


# ---------------------------------------------------------------------------
# _match_canonical — word-boundary correctness
# ---------------------------------------------------------------------------


class TestMatchCanonical:
    def test_mit_full_name(self) -> None:
        assert _match_canonical("Massachusetts Institute of Technology") == "MIT"

    def test_carnegie_mellon(self) -> None:
        assert _match_canonical("Carnegie Mellon University") == "CMU"

    def test_google_deepmind_specific_wins_over_google(self) -> None:
        # More-specific entry must come before the generic "google" entry
        assert _match_canonical("Google DeepMind") == "Google DeepMind"

    def test_intel_does_not_fire_on_artificial_intelligence(self) -> None:
        # 'intel' is a substring of 'intelligence' — boundary check must reject this
        result = _match_canonical("artificial intelligence")
        assert result != "Intel"

    def test_meta_does_not_fire_on_metadata(self) -> None:
        result = _match_canonical("metadata analysis framework")
        assert result != "Meta"

    def test_no_match_returns_none(self) -> None:
        assert _match_canonical("Some Random Org With No Match") is None

    def test_case_insensitive(self) -> None:
        assert _match_canonical("STANFORD UNIVERSITY") == "Stanford"

    def test_harvard_matched(self) -> None:
        assert _match_canonical("Harvard University") == "Harvard"


# ---------------------------------------------------------------------------
# _get_with_retry
# ---------------------------------------------------------------------------


async def test_get_with_retry_succeeds_on_first_attempt(respx_mock) -> None:
    """A normal 200 response is returned immediately without retrying."""
    respx_mock.get(_RE_S2).mock(return_value=Response(200, json={"data": []}))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.semanticscholar.org/test", {})
    assert resp is not None
    assert resp.status_code == 200


async def test_get_with_retry_retries_on_429_then_succeeds(respx_mock) -> None:
    """A 429 followed by a 200 should succeed after one retry (Retry-After: 0)."""
    respx_mock.get(_RE_S2).mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json={"data": ["result"]}),
        ]
    )
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.semanticscholar.org/test", {})
    assert resp is not None
    assert resp.status_code == 200


async def test_get_with_retry_all_429_returns_none(respx_mock) -> None:
    """When every attempt returns 429, _get_with_retry returns None."""
    respx_mock.get(_RE_S2).mock(
        return_value=Response(429, headers={"Retry-After": "0"})
    )
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(
            client, "https://api.semanticscholar.org/test", {}, context="test"
        )
    assert resp is None


async def test_get_with_retry_network_error_returns_none(respx_mock) -> None:
    """A network-level error (httpx.RequestError) returns None immediately."""
    respx_mock.get(_RE_S2).mock(side_effect=httpx.ConnectError("timeout"))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.semanticscholar.org/test", {})
    assert resp is None


async def test_get_with_retry_persistent_500_returns_last_response(respx_mock) -> None:
    """A 5xx is retried; if it never recovers the final response is returned."""
    route = respx_mock.get(_RE_S2).mock(return_value=Response(500))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.semanticscholar.org/test", {})
    assert resp is not None
    assert resp.status_code == 500
    assert route.call_count == 4


async def test_get_with_retry_404_returned_immediately(respx_mock) -> None:
    """A 404 is returned as-is (not retried)."""
    respx_mock.get(_RE_S2).mock(return_value=Response(404))
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, "https://api.semanticscholar.org/test", {})
    assert resp is not None
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rate limits are failures, not "not found"
# ---------------------------------------------------------------------------


async def test_resolve_rate_limited_raises_instead_of_not_found(respx_mock) -> None:
    """Last night's logs showed 429s reported as "paper not found"; that hid
    the paper's citations. Exhausted rate limits must raise."""
    respx_mock.post(_RE_S2).mock(return_value=Response(429, headers={"Retry-After": "0"}))
    with pytest.raises(SourceUnavailable):
        await _resolve_s2_paper_id("10.1234/abc")


async def test_resolve_rate_limit_then_success(respx_mock) -> None:
    respx_mock.post(_RE_S2).mock(side_effect=[
        Response(429, headers={"Retry-After": "0"}),
        Response(200, json=[{"paperId": "p1"}]),
    ])
    assert await _resolve_s2_paper_id("10.1234/abc") == "p1"


async def test_resolve_unknown_id_is_not_found(respx_mock) -> None:
    """S2 answers 400 for identifiers it doesn't know: genuinely not found."""
    respx_mock.post(_RE_S2).mock(return_value=Response(400))
    assert await _resolve_s2_paper_id("10.18429/jacow-napac2025-tup099") is None


async def test_citing_papers_failed_page_raises(respx_mock) -> None:
    respx_mock.post(_RE_S2).mock(return_value=Response(200, json=[{"paperId": "p1"}]))
    respx_mock.get(_RE_S2).mock(return_value=Response(503))
    with pytest.raises(SourceUnavailable):
        await get_citing_papers("10.1234/abc")


async def test_citation_counts_match_by_position_not_returned_doi(respx_mock) -> None:
    """For an arXiv paper S2 reports the journal DOI; the count must still be
    filed under the DOI we asked about."""
    respx_mock.post(_RE_S2).mock(return_value=Response(200, json=[
        {"paperId": "a", "citationCount": 12, "externalIds": {"DOI": "10.1103/physrevd.1"}},  # ARXIV:2506.02005
        {"paperId": "a", "citationCount": 12, "externalIds": {"DOI": "10.1103/physrevd.1"}},  # DOI:10.48550/…
        None,                                                                                  # DOI:10.1/missing
    ]))
    counts = await get_citation_counts(["10.48550/arXiv.2506.02005", "10.1/missing"])
    assert counts == {"10.48550/arxiv.2506.02005": 12}


async def test_citation_counts_failed_batch_returns_empty(respx_mock) -> None:
    respx_mock.post(_RE_S2).mock(return_value=Response(429, headers={"Retry-After": "0"}))
    assert await get_citation_counts(["10.1/a"]) == {}

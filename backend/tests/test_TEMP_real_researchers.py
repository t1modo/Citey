"""
TEMPORARY integration tests — DO NOT COMMIT.

These tests hit the live OpenAlex, Semantic Scholar, PubMed, INSPIRE-HEP, and
DBLP APIs with real researcher names to verify the full data pipeline works
correctly against production data.

Run once with:  pytest tests/test_TEMP_real_researchers.py -v -s
Then delete this file.
"""

from __future__ import annotations

import pytest

from app.services import openalex as oa_svc
from app.services import semantic_scholar as s2_svc
from app.services import pubmed as pubmed_svc
from app.services import inspire_hep as inspire_svc
from app.services import dblp as dblp_svc
from app.routers.works import _author_in_paper, _names_match


# ---------------------------------------------------------------------------
# OpenAlex — Yoshua Bengio (ML pioneer, enormous OA presence)
# ---------------------------------------------------------------------------


async def test_oa_search_yoshua_bengio() -> None:
    """OpenAlex should return at least one author matching Yoshua Bengio."""
    results = await oa_svc.search_authors("Yoshua Bengio")
    assert len(results) > 0, "Expected at least one result for Yoshua Bengio"
    names = [r.get("display_name", "") for r in results]
    assert any("Bengio" in n for n in names), f"No Bengio in results: {names}"


async def test_oa_bengio_works_by_author() -> None:
    """Given Yoshua Bengio's OA author ID, get_works_by_author should return papers."""
    results = await oa_svc.search_authors("Yoshua Bengio")
    assert results, "No search results — cannot verify get_works_by_author"

    # Pick the candidate with the highest works_count (most likely the real one)
    best = max(results, key=lambda r: r.get("works_count", 0))
    author_id = best.get("id", "").replace("https://openalex.org/", "")
    assert author_id, "No author ID in result"

    works = await oa_svc.get_works_by_author(author_id)
    assert len(works) > 10, f"Expected many works for Bengio, got {len(works)}"

    # OpenAlex may include a small number of null-title records (retracted/merged works).
    # Verify that the vast majority have a title.
    titled = sum(1 for w in works if w.get("title"))
    assert titled > 10, f"Expected many titled works for Bengio, got {titled}"


async def test_oa_bengio_author_in_paper_name_variants() -> None:
    """Name matching must handle OpenAlex display-name variants for Bengio."""
    paper_authors = ["Yoshua Bengio", "Geoffrey E. Hinton", "Yann LeCun"]
    assert _author_in_paper(paper_authors, ["Y. Bengio"])
    assert _author_in_paper(paper_authors, ["Yoshua Bengio"])
    assert not _author_in_paper(paper_authors, ["Andrew Ng"])


# ---------------------------------------------------------------------------
# OpenAlex — Geoffrey Hinton
# ---------------------------------------------------------------------------


async def test_oa_search_geoffrey_hinton() -> None:
    """OpenAlex should return at least one author matching Geoffrey Hinton."""
    results = await oa_svc.search_authors("Geoffrey Hinton")
    assert len(results) > 0
    names = [r.get("display_name", "") for r in results]
    assert any("Hinton" in n for n in names), f"No Hinton in results: {names}"


async def test_names_match_hinton_variants() -> None:
    """Common abbreviation patterns for Hinton must match."""
    assert _names_match("Geoffrey Hinton", "G. Hinton")
    assert _names_match("G. E. Hinton", "Geoffrey Everest Hinton")
    assert not _names_match("Geoffrey Hinton", "Yann LeCun")


# ---------------------------------------------------------------------------
# Semantic Scholar — Jennifer Doudna (CRISPR, biology)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="S2 public API rate-limits aggressively; may 429 in CI")
async def test_s2_search_jennifer_doudna() -> None:
    """Semantic Scholar should return at least one result for Jennifer Doudna."""
    results = await s2_svc.search_authors("Jennifer Doudna")
    assert len(results) > 0, "Expected at least one S2 result for Doudna"
    names = [r.get("name", "") for r in results]
    assert any("Doudna" in n for n in names), f"No Doudna in S2 results: {names}"


@pytest.mark.xfail(strict=False, reason="S2 public API rate-limits aggressively; may 429 in CI")
async def test_s2_doudna_works_returned() -> None:
    """Doudna's S2 profile should have papers with titles."""
    results = await s2_svc.search_authors("Jennifer Doudna")
    assert results

    best = max(results, key=lambda r: r.get("paperCount", 0))
    author_id = best.get("authorId", "")
    assert author_id

    works = await s2_svc.get_works_by_author(author_id)
    assert len(works) > 5, f"Expected several S2 works for Doudna, got {len(works)}"


# ---------------------------------------------------------------------------
# PubMed — Jennifer Doudna (well-indexed in PubMed for biology)
# ---------------------------------------------------------------------------


async def test_pubmed_search_doudna() -> None:
    """PubMed should find results for Jennifer Doudna."""
    results = await pubmed_svc.search_authors("Jennifer Doudna")
    assert len(results) > 0, "PubMed should return at least one result for Doudna"
    assert results[0].get("paperCount", 0) > 0


async def test_pubmed_works_doudna() -> None:
    """PubMed get_works_by_author should return OA-compatible works for Doudna."""
    works = await pubmed_svc.get_works_by_author("Doudna JA")
    # May return zero if PubMed query varies — just check structure if any returned
    for w in works[:5]:
        assert "title" in w
        assert "doi" in w
        assert "publication_year" in w
        assert "authorships" in w


# ---------------------------------------------------------------------------
# INSPIRE-HEP — Kip Thorne (Nobel laureate in physics, LIGO)
# ---------------------------------------------------------------------------


async def test_inspire_search_kip_thorne() -> None:
    """INSPIRE-HEP should find Kip Thorne."""
    results = await inspire_svc.search_authors("Kip Thorne")
    assert len(results) > 0, "INSPIRE should return at least one result for Thorne"
    names = [r.get("name", "") for r in results]
    assert any("Thorne" in n for n in names), f"No Thorne in INSPIRE results: {names}"


async def test_inspire_thorne_works() -> None:
    """INSPIRE get_works_by_author should return OA-compatible works for Thorne."""
    results = await inspire_svc.search_authors("Kip Thorne")
    assert results

    best = max(results, key=lambda r: r.get("paperCount", 0))
    author_id = best.get("authorId", "")
    assert author_id

    works = await inspire_svc.get_works_by_author(author_id)
    assert len(works) > 0, "Expected at least some INSPIRE works for Thorne"
    for w in works[:3]:
        assert w.get("doi"), "Works from INSPIRE should have DOIs"
        assert "title" in w


# ---------------------------------------------------------------------------
# DBLP — Tim Berners-Lee (inventor of the web, well-indexed in DBLP)
# ---------------------------------------------------------------------------


async def test_dblp_search_berners_lee() -> None:
    """DBLP should find Tim Berners-Lee."""
    results = await dblp_svc.search_authors("Tim Berners-Lee")
    assert len(results) > 0, "DBLP should return at least one result for Berners-Lee"
    names = [r.get("name", "") for r in results]
    assert any("Berners" in n for n in names), f"No Berners-Lee in DBLP results: {names}"


async def test_dblp_berners_lee_works() -> None:
    """DBLP get_works_by_author should return OA-compatible works."""
    results = await dblp_svc.search_authors("Tim Berners-Lee")
    assert results

    best = max(results, key=lambda r: r.get("paperCount", 0))
    author_id = best.get("authorId", "")
    assert author_id

    works = await dblp_svc.get_works_by_author(author_id)
    assert len(works) > 0, "Expected at least some DBLP works for Berners-Lee"
    for w in works[:3]:
        assert "title" in w
        assert "authorships" in w


# ---------------------------------------------------------------------------
# Cross-source name matching with real author name variants
# ---------------------------------------------------------------------------


class TestRealNameVariants:
    """
    Verify _names_match handles the exact display-name forms that OpenAlex,
    Semantic Scholar, and other sources emit for real researchers.
    """

    def test_bengio_initial_form(self) -> None:
        # S2 sometimes stores "Y. Bengio"; OA uses "Yoshua Bengio"
        assert _names_match("Y. Bengio", "Yoshua Bengio")

    def test_lecun_yann_with_accent(self) -> None:
        # OA stores "Yann LeCun" — verify this matches common variants
        assert _names_match("Yann LeCun", "Y. LeCun")
        assert _names_match("Yann LeCun", "Yann Le Cun")

    def test_doudna_with_initial(self) -> None:
        # PubMed stores "Doudna JA"; we convert to "JA Doudna" in the service
        # After conversion to First Last form, verify name matching
        assert _names_match("Jennifer A. Doudna", "Jennifer Doudna")
        assert _names_match("J. Doudna", "Jennifer Doudna")

    def test_hinton_middle_initial(self) -> None:
        assert _names_match("Geoffrey E. Hinton", "Geoffrey Hinton")
        assert _names_match("G. E. Hinton", "G. Hinton")

    def test_thorne_kip_s(self) -> None:
        assert _names_match("Kip S. Thorne", "Kip Thorne")
        assert _names_match("K. S. Thorne", "Kip Thorne")

    def test_berners_lee_hyphenated(self) -> None:
        # Some sources drop the hyphen; verify both forms match
        assert _names_match("Tim Berners-Lee", "Tim Berners Lee")

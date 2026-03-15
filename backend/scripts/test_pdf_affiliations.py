#!/usr/bin/env python3
"""
Test PDF affiliation extraction for citing papers.
Usage: python scripts/test_pdf_affiliations.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.services.semantic_scholar import (
    get_citing_papers,
    normalize_citing_work,
    _extract_affiliations_from_arxiv_pdf,
)

# The two ArXiv IDs of papers that cite the test paper
TEST_ARXIV_IDS = [
    "2502.12345",  # placeholder — will be discovered via get_citing_papers
]

TEST_DOI = "10.18653/v1/2025.uncertainlp-main.23"


async def main() -> None:
    print(f"Fetching citing papers for DOI: {TEST_DOI}\n")
    raw_papers = await get_citing_papers(TEST_DOI)
    print(f"Found {len(raw_papers)} citing paper(s)\n")

    for i, raw in enumerate(raw_papers, 1):
        norm = normalize_citing_work(raw)
        ext = raw.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv") or ext.get("arxiv") or ""
        pdf_affils = raw.get("_pdf_affiliations") or []

        print(f"--- Paper {i} ---")
        print(f"  Title       : {norm['title'][:80]}")
        print(f"  ArXiv ID    : {arxiv_id or '(none)'}")
        print(f"  S2 Affiliations  : {norm['affiliations']}")
        print(f"  PDF Affiliations : {pdf_affils}")
        print()


if __name__ == "__main__":
    asyncio.run(main())

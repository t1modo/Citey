#!/usr/bin/env python3
"""
Diagnostic: compare OpenAlex and S2 coverage for a given author name.

Shows every paper found in each source, highlights the DOI overlap that
triggers the cross-source safety check, and flags papers that are only
present in one source (the ones that would be missed without the boost).

Usage:
    cd backend
    python scripts/check_author_coverage.py "Timothy Do"
    python scripts/check_author_coverage.py "Timothy Khang Do"
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from the backend/ directory without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.works import _names_match
from app.services import openalex as oa_svc
from app.services import semantic_scholar as s2_svc


def _strip_doi(doi: str | None) -> str | None:
    if not doi:
        return doi
    for pfx in ("https://doi.org/", "http://doi.org/"):
        if doi.startswith(pfx):
            return doi[len(pfx):]
    return doi


def _dois(works: list[dict]) -> dict[str, str]:
    """Return {normalised_doi: title} for a list of works."""
    result: dict[str, str] = {}
    for w in works:
        d = _strip_doi(w.get("doi"))
        if d:
            result[d.lower()] = (w.get("title") or "").strip()
    return result


async def main(author_name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Author coverage report for: {author_name!r}")
    print(f"{'='*60}\n")

    # ── Search both sources in parallel ──────────────────────────────────────
    oa_candidates, s2_candidates = await asyncio.gather(
        oa_svc.search_authors(author_name),
        s2_svc.search_authors(author_name),
    )

    print(f"OpenAlex candidates ({len(oa_candidates)} returned):")
    for c in oa_candidates[:5]:
        name = c.get("display_name", "?")
        match = _names_match(name, author_name)
        print(f"  {'✓' if match else '✗'} {name!r}  ({c.get('works_count', '?')} works)  [{c.get('id', '')}]")

    print(f"\nSemantic Scholar candidates ({len(s2_candidates)} returned):")
    for c in s2_candidates[:5]:
        name = c.get("name", "?")
        match = _names_match(name, author_name)
        print(f"  {'✓' if match else '✗'} {name!r}  ({c.get('paperCount', '?')} papers)  [S2:{c.get('authorId', '')}]")

    # ── Pick first matching candidate from each source ────────────────────────
    oa_match = next(
        (c for c in oa_candidates[:3] if _names_match(c.get("display_name", ""), author_name)),
        None,
    )
    s2_match = next(
        (c for c in s2_candidates[:3] if _names_match(c.get("name", ""), author_name)),
        None,
    )

    oa_doi_map: dict[str, str] = {}
    s2_doi_map: dict[str, str] = {}

    # ── Fetch works ───────────────────────────────────────────────────────────
    if oa_match:
        print(f"\n{'─'*60}")
        print(f"OpenAlex works for {oa_match['display_name']!r}  [{oa_match['id']}]")
        print(f"{'─'*60}")
        oa_works = await oa_svc.get_works_by_author(oa_match["id"])
        oa_doi_map = _dois(oa_works)
        print(f"  Total: {len(oa_works)} works  ({len(oa_doi_map)} with DOIs)\n")
        for doi, title in sorted(oa_doi_map.items()):
            print(f"  {doi}")
            print(f"    {title[:80]}")
    else:
        print("\n  No OpenAlex name match — skipping OA fetch.")

    if s2_match:
        print(f"\n{'─'*60}")
        print(f"S2 works for {s2_match['name']!r}  [S2:{s2_match['authorId']}]")
        print(f"{'─'*60}")
        s2_works = await s2_svc.get_works_by_author(s2_match["authorId"])
        s2_doi_map = _dois(s2_works)
        print(f"  Total: {len(s2_works)} works  ({len(s2_doi_map)} with DOIs)\n")
        for doi, title in sorted(s2_doi_map.items()):
            print(f"  {doi}")
            print(f"    {title[:80]}")
    else:
        print("\n  No S2 name match — skipping S2 fetch.")

    # ── Coverage summary ──────────────────────────────────────────────────────
    if oa_doi_map and s2_doi_map:
        overlap = set(oa_doi_map) & set(s2_doi_map)
        only_oa = set(oa_doi_map) - set(s2_doi_map)
        only_s2 = set(s2_doi_map) - set(oa_doi_map)

        print(f"\n{'='*60}")
        print(f"  Coverage summary")
        print(f"{'='*60}")
        print(f"  Shared DOIs (overlap):   {len(overlap)}")
        print(f"  Only in OpenAlex:        {len(only_oa)}")
        print(f"  Only in S2:              {len(only_s2)}")

        if overlap:
            print(f"\n  Cross-source safety check would PASS ({len(overlap)} shared DOI(s))")
            print(f"  → The {len(only_oa)} OA-only and {len(only_s2)} S2-only paper(s) would be imported.")
        else:
            print(f"\n  ⚠ Cross-source safety check would FAIL (0 shared DOIs)")
            print(f"  → Extra works would NOT be merged (different researcher?)")

        if only_oa:
            print(f"\n  Papers only in OpenAlex (would be gained by cross-source):")
            for doi in sorted(only_oa):
                print(f"    {doi}")
                print(f"      {oa_doi_map[doi][:80]}")

        if only_s2:
            print(f"\n  Papers only in S2 (would be gained by cross-source):")
            for doi in sorted(only_s2):
                print(f"    {doi}")
                print(f"      {s2_doi_map[doi][:80]}")
    elif oa_doi_map or s2_doi_map:
        print("\n  Only one source returned results — no overlap comparison possible.")

    print()


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Timothy Do"
    asyncio.run(main(query))

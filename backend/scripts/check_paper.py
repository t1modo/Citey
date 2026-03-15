#!/usr/bin/env python3
"""
Check what OA and S2 know about a paper and its citations.
Usage: python scripts/check_paper.py <doi>
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

import httpx

async def main(doi: str) -> None:
    clean = doi.replace("https://doi.org/", "")
    print(f"\nChecking: {clean}\n")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # OA: look up the paper itself
        r = await client.get(
            "https://api.openalex.org/works",
            params={"filter": f"doi:https://doi.org/{clean}", "per_page": 1,
                    "mailto": "support@citey.app"},
        )
        works = r.json().get("results", [])
        if not works:
            print("OpenAlex: paper NOT found by DOI")
        else:
            w = works[0]
            oa_id = w.get("id", "").replace("https://openalex.org/", "")
            print(f"OpenAlex paper found: {oa_id}")
            print(f"  title      : {w.get('title')}")
            print(f"  cited_by   : {w.get('cited_by_count', 0)}")
            print(f"  pub_date   : {w.get('publication_date')}")

            # OA: fetch citing works (no date filter)
            r2 = await client.get(
                "https://api.openalex.org/works",
                params={"filter": f"cites:{oa_id}", "per_page": 10,
                        "mailto": "support@citey.app"},
            )
            citing = r2.json().get("results", [])
            meta = r2.json().get("meta", {})
            print(f"\nOpenAlex citing works: {meta.get('count', 0)} total")
            for c in citing[:5]:
                print(f"  - {c.get('title','')[:70]}  ({c.get('publication_date','')})")

        # S2: batch resolve
        print()
        candidates = [f"DOI:{clean}"]
        if clean.lower().startswith("10.48550/arxiv."):
            candidates.insert(0, f"ARXIV:{clean.split('/arxiv.',1)[1]}")
        r3 = await client.post(
            "https://api.semanticscholar.org/graph/v1/paper/batch",
            params={"fields": "paperId,title,citationCount"},
            json={"ids": candidates},
            headers={"User-Agent": "Citey/0.1 (mailto:support@citey.app)"},
        )
        print(f"S2 batch status: {r3.status_code}")
        if r3.status_code == 200:
            for item in r3.json():
                if item:
                    print(f"  S2 paperId     : {item.get('paperId')}")
                    print(f"  S2 title       : {item.get('title','')[:70]}")
                    print(f"  S2 citationCount: {item.get('citationCount')}")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else
                     "10.18653/v1/2025.uncertainlp-main.23"))

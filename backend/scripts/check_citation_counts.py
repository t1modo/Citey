#!/usr/bin/env python3
"""
Debug script: prints citation counts per source for all tracked works.
Run from backend/: python scripts/check_citation_counts.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

import httpx
from app.firebase_client import get_db


async def fetch_oa_count(client: httpx.AsyncClient, openalex_id: str) -> int | None:
    short = openalex_id.replace("https://openalex.org/", "")
    try:
        r = await client.get(
            f"https://api.openalex.org/works/{short}",
            params={"select": "id,cited_by_count", "mailto": "support@citey.app"},
        )
        if r.status_code == 200:
            return r.json().get("cited_by_count")
        print(f"    OA HTTP {r.status_code} for {short}")
    except Exception as e:
        print(f"    OA error: {e}")
    return None


async def fetch_crossref_count(client: httpx.AsyncClient, doi: str) -> int | None:
    try:
        r = await client.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "Citey/0.1 (mailto:support@citey.app)"},
        )
        if r.status_code == 200:
            return r.json().get("message", {}).get("is-referenced-by-count")
        print(f"    Crossref HTTP {r.status_code} for {doi}")
    except Exception as e:
        print(f"    Crossref error: {e}")
    return None


async def main() -> None:
    db = get_db()

    async with httpx.AsyncClient(timeout=15.0) as client:
        for user_doc in db.collection("users").stream():
            uid = user_doc.id
            user_data = user_doc.to_dict() or {}
            email = user_data.get("email", "")
            print(f"\n{'='*70}")
            print(f"User: {email}  (uid={uid})")

            works = [
                (w.id, w.to_dict() or {})
                for w in db.collection("users").document(uid).collection("trackedWorks").stream()
            ]
            print(f"Tracked works: {len(works)}\n")

            total_s2 = 0
            total_oa_stored = 0
            total_oa_live = 0
            total_crossref = 0

            for wid, wdata in works:
                doi = wdata.get("doi", "")
                oa_id = wdata.get("openalex_id", "")
                s2 = wdata.get("s2_citation_count") or 0
                oa_stored = wdata.get("openalex_citation_count") or 0

                oa_live = await fetch_oa_count(client, oa_id) if oa_id else None
                crossref = await fetch_crossref_count(client, doi) if doi else None

                total_s2 += s2
                total_oa_stored += oa_stored
                total_oa_live += oa_live or 0
                total_crossref += crossref or 0

                print(f"  {wdata.get('title', 'Untitled')[:60]}")
                print(f"    S2={s2}  OA_stored={oa_stored}  OA_live={oa_live}  Crossref={crossref}")

            print(f"\n  TOTALS: S2={total_s2}  OA_stored={total_oa_stored}  "
                  f"OA_live={total_oa_live}  Crossref={total_crossref}")


if __name__ == "__main__":
    asyncio.run(main())

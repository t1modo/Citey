#!/usr/bin/env python3
"""
Diagnose why citation check returns 0 for a specific DOI.

Usage:
    python scripts/debug_citations.py <doi>

Example:
    python scripts/debug_citations.py 10.18653/v1/2024.acl-long.206
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

import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

import httpx
from app.firebase_client import get_db
from app.services import openalex as oa_svc
from app.services import semantic_scholar as s2_svc


async def main(doi: str) -> None:
    db = get_db()

    print(f"\n{'='*60}")
    print(f"Diagnosing DOI: {doi}")
    print(f"{'='*60}\n")

    # 1. Find the work in Firestore (scan all users)
    work_id = doi.replace("/", "__")
    print(f"Expected Firestore work ID: {work_id}")

    work_doc = None
    uid = None
    for user_doc in db.collection("users").stream():
        ref = user_doc.reference.collection("trackedWorks").document(work_id)
        snap = ref.get()
        if snap.exists:
            work_doc = snap.to_dict()
            uid = user_doc.id
            break

    if not work_doc:
        print("ERROR: Work not found in Firestore for any user.")
        return

    print(f"\n[Firestore trackedWork]")
    print(f"  uid              : {uid}")
    print(f"  doi              : {work_doc.get('doi')}")
    print(f"  openalex_id      : {work_doc.get('openalex_id')}")
    print(f"  last_checked_at  : {work_doc.get('last_checked_at')}")
    print(f"  title            : {work_doc.get('title')}")

    openalex_id = work_doc.get("openalex_id")

    # 2. Resolve OA ID if missing
    if not openalex_id:
        print(f"\n[OA resolve] openalex_id missing — resolving from DOI...")
        raw = await oa_svc.get_work_by_doi(doi)
        if raw:
            openalex_id = raw.get("id")
            print(f"  Resolved: {openalex_id}")
        else:
            print("  ERROR: OA returned nothing for this DOI.")

    # 3. OpenAlex citation fetch
    print(f"\n[OpenAlex] Fetching citing works for openalex_id={openalex_id}")
    if openalex_id:
        oa_results = await oa_svc.get_citing_works(openalex_id, since_date=None)
        print(f"  OA citing works count: {len(oa_results)}")
        for i, r in enumerate(oa_results[:5]):
            print(f"  [{i}] doi={r.get('doi')}  title={r.get('title', '')[:60]}")
    else:
        oa_results = []
        print("  SKIPPED — no openalex_id")

    # 4. Semantic Scholar citation fetch (raw httpx, to confirm URL encoding)
    print(f"\n[S2 raw httpx] Testing URL encoding for doi={doi}")
    clean = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
    from urllib.parse import quote
    paper_id = quote(f"DOI:{clean}", safe=":")
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
    print(f"  URL: {url}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"fields": "paperId,title", "limit": 5})
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  S2 citing papers count (offset 0): {len(data.get('data', []))}")
    else:
        print(f"  Body: {resp.text[:300]}")

    # 5. S2 via service function
    print(f"\n[S2 service] get_citing_papers('{doi}')")
    s2_results = await s2_svc.get_citing_papers(doi)
    print(f"  S2 service citing works count: {len(s2_results)}")

    # 6. Existing notifications in Firestore
    print(f"\n[Firestore notifications] for cited_work_id={work_id}")
    notifs_ref = db.collection("users").document(uid).collection("notifications")
    notif_docs = list(notifs_ref.where("cited_work_id", "==", work_id).stream())
    print(f"  Existing notification count: {len(notif_docs)}")
    for ndoc in notif_docs[:5]:
        d = ndoc.to_dict() or {}
        print(f"    id={ndoc.id}  doi={d.get('citing_work_doi')}  title={str(d.get('citing_work_title',''))[:40]}")

    # 7. Normalise and dedup to see final merged list
    print(f"\n[Dedup/merge]")
    from app.services.citation_service import _dedup_key
    oa_norm = [oa_svc.normalize_citing_work(r) for r in oa_results]
    s2_norm = [s2_svc.normalize_citing_work(r) for r in s2_results]
    merged: dict = {}
    for n in oa_norm:
        key = _dedup_key(n)
        if key:
            merged[key] = n
    for n in s2_norm:
        key = _dedup_key(n)
        if key and key not in merged:
            merged[key] = n
    print(f"  OA normalized: {len(oa_norm)}")
    print(f"  S2 normalized: {len(s2_norm)}")
    print(f"  Merged unique : {len(merged)}")
    for key, n in list(merged.items())[:5]:
        print(f"    key={key}  title={n.get('title','')[:60]}")

    # 8. Simulate doc_id computation and existing_ids check
    print(f"\n[Doc ID simulation]")
    from app.services.citation_service import _safe_doc_id
    existing_ids: set[str] = set()
    for ndoc in notif_docs:
        d = ndoc.to_dict() or {}
        citing_doi_stored = d.get("citing_work_doi") or ""
        canonical_id = (
            f"{work_id}__{_safe_doc_id(citing_doi_stored)}"
            if citing_doi_stored else ndoc.id
        )
        existing_ids.add(canonical_id)
    print(f"  existing_ids (canonical): {existing_ids}")
    is_fresh = work_doc.get("last_checked_at") is None
    print(f"  is_fresh_add: {is_fresh}")

    would_write = 0
    would_skip = 0
    for n in merged.values():
        citing_doi = n.get("doi") or ""
        citing_id = citing_doi or n.get("id") or ""
        if not citing_id:
            print(f"  SKIP (no ID): {n.get('title')}")
            continue
        doc_id = f"{work_id}__{_safe_doc_id(citing_id)}"
        if is_fresh:
            # stale wipe, existing_ids is empty
            print(f"  WOULD WRITE (fresh add): {doc_id}")
            would_write += 1
        elif doc_id in existing_ids:
            print(f"  SKIP (exists): {doc_id}")
            would_skip += 1
        else:
            print(f"  WOULD WRITE: {doc_id}")
            would_write += 1

    print(f"\n  Summary: would_write={would_write}, would_skip={would_skip}")
    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/debug_citations.py <doi>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))

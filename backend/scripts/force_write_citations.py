#!/usr/bin/env python3
"""
Force-fetch and write citations for a specific DOI, for all users tracking it.
Usage: python scripts/force_write_citations.py <doi>
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.firebase_client import get_db
from app.services.citation_service import process_tracked_work, _doc_to_tracked_work


async def main(doi: str) -> None:
    db = get_db()
    work_id = doi.replace("/", "__")
    print(f"\nForce-writing citations for DOI: {doi}")
    print(f"Firestore work ID: {work_id}\n")

    found_any = False
    for user_doc in db.collection("users").stream():
        uid = user_doc.id
        ref = user_doc.reference.collection("trackedWorks").document(work_id)
        snap = ref.get()
        if not snap.exists:
            continue

        found_any = True
        wdata = snap.to_dict() or {}

        # Force fresh-add by wiping last_checked_at so existing_ids stays empty
        ref.update({"last_checked_at": None})
        wdata["last_checked_at"] = None

        # Also delete any existing notifications so we start clean
        notifs_ref = user_doc.reference.collection("notifications")
        deleted = 0
        for ndoc in notifs_ref.where("cited_work_id", "==", work_id).stream():
            ndoc.reference.delete()
            deleted += 1
        if deleted:
            print(f"Cleared {deleted} existing notification(s) for uid={uid}")

        work = _doc_to_tracked_work(work_id, wdata)
        print(f"Processing uid={uid} ...")
        count, notifications = await process_tracked_work(
            uid=uid, work=work, db=db, dry_run=False
        )
        print(f"  Written: {count} new notification(s)")
        for n in notifications:
            print(f"    - {n.citing_work_title[:70]}")
            print(f"      DOI: {n.citing_work_doi}")
            print(f"      Authors: {', '.join(n.citing_authors[:3])}")

    if not found_any:
        print(f"ERROR: No user is tracking DOI '{doi}'")


if __name__ == "__main__":
    doi = sys.argv[1] if len(sys.argv) > 1 else "10.18653/v1/2025.uncertainlp-main.23"
    asyncio.run(main(doi))

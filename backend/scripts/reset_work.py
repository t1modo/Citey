#!/usr/bin/env python3
"""
Reset a tracked work so the next citation check treats it as freshly added.

- Deletes ALL existing notifications for the work (regardless of doc ID format).
- Sets last_checked_at to null on the trackedWork document.

Usage:
    python scripts/reset_work.py <doi>

Example:
    python scripts/reset_work.py 10.18653/v1/2024.acl-long.206
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from app.firebase_client import get_db


def reset_work(doi: str) -> None:
    db = get_db()
    work_id = doi.replace("/", "__")
    print(f"Resetting work: {work_id}")

    # Find the user who owns this work.
    uid = None
    for user_doc in db.collection("users").stream():
        ref = user_doc.reference.collection("trackedWorks").document(work_id)
        if ref.get().exists:
            uid = user_doc.id
            break

    if not uid:
        print(f"ERROR: Work '{work_id}' not found for any user.")
        sys.exit(1)

    print(f"Found work for uid={uid}")

    # Delete all notifications for this work (any doc ID format).
    notifs_ref = db.collection("users").document(uid).collection("notifications")
    deleted = 0
    for ndoc in notifs_ref.where("cited_work_id", "==", work_id).stream():
        print(f"  Deleting notification: {ndoc.id}")
        ndoc.reference.delete()
        deleted += 1

    print(f"Deleted {deleted} notification(s).")

    # Reset last_checked_at to null so the next check is a fresh add.
    db.collection("users").document(uid).collection("trackedWorks").document(work_id).update(
        {"last_checked_at": None}
    )
    print("Reset last_checked_at to null.")
    print("Done — run citation check now to re-discover citations.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/reset_work.py <doi>")
        sys.exit(1)
    reset_work(sys.argv[1])

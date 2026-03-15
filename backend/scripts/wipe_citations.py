#!/usr/bin/env python3
"""
Wipe all notifications and reset last_checked_at for all tracked works.

This gives a completely blank slate — the next citation check will
re-discover and re-write all citations from scratch.

Usage:
    python scripts/wipe_citations.py
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


def wipe_citations() -> None:
    db = get_db()

    total_notifs = 0
    total_works = 0

    for user_doc in db.collection("users").stream():
        uid = user_doc.id
        user_ref = user_doc.reference

        # Delete all notifications.
        notifs = list(user_ref.collection("notifications").stream())
        for ndoc in notifs:
            ndoc.reference.delete()
        total_notifs += len(notifs)
        if notifs:
            print(f"  uid={uid}: deleted {len(notifs)} notification(s)")

        # Reset last_checked_at on every tracked work.
        works = list(user_ref.collection("trackedWorks").stream())
        for wdoc in works:
            wdoc.reference.update({"last_checked_at": None})
        total_works += len(works)
        if works:
            print(f"  uid={uid}: reset {len(works)} tracked work(s)")

    print(f"\nDone. Deleted {total_notifs} notification(s), reset {total_works} tracked work(s).")
    print("Run citation check to re-discover all citations.")


if __name__ == "__main__":
    confirm = input("This will delete ALL notifications and reset all check timestamps. Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)
    wipe_citations()

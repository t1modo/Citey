#!/usr/bin/env python3
"""
Delete a user from Firebase Auth and Firestore by email address.

Usage:
    python scripts/delete_user.py <email>

Example:
    python scripts/delete_user.py timodo.alt.acc@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

import firebase_admin.auth as fb_auth
from app.firebase_client import get_db


def delete_user(email: str) -> None:
    db = get_db()

    # 1. Look up the user in Firebase Auth by email.
    try:
        user_record = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        print(f"No Firebase Auth user found with email: {email}")
        sys.exit(1)

    uid = user_record.uid
    print(f"Found user: uid={uid}  email={email}")

    confirm = input("Delete this user and all their Firestore data? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # 2. Delete Firestore subcollections and the user document.
    user_ref = db.collection("users").document(uid)

    for subcol in ("trackedWorks", "notifications"):
        docs = user_ref.collection(subcol).stream()
        deleted = 0
        for doc in docs:
            doc.reference.delete()
            deleted += 1
        print(f"  Deleted {deleted} document(s) from users/{uid}/{subcol}")

    user_ref.delete()
    print(f"  Deleted Firestore document users/{uid}")

    # 3. Delete from Firebase Auth.
    fb_auth.delete_user(uid)
    print(f"  Deleted Firebase Auth user uid={uid}")

    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/delete_user.py <email>")
        sys.exit(1)
    delete_user(sys.argv[1])

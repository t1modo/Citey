#!/usr/bin/env python3
"""
Send the "Citey has been rebuilt" email to registered users.

Dry run by default: lists who would receive it and sends nothing.

  python scripts/send_announcement.py                 # dry run, prints recipients
  python scripts/send_announcement.py --to me@x.edu   # send one test copy
  python scripts/send_announcement.py --send          # send to everyone

Skips users who unsubscribed (notify_enabled false), Firestore users whose
Firebase account no longer exists, and repeated addresses. Needs the same
environment as the API (Firebase credentials and RESEND_API_KEY).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from app.config import get_settings  # noqa: E402
from app.firebase_client import get_db  # noqa: E402
from app.services.citation_service import _get_auth_uids  # noqa: E402
from app.services.email_service import resolve_recipient, send_announcement_email  # noqa: E402

# Resend allows a few requests per second; stay well under it.
_PAUSE_SECONDS = 0.6


def recipients(db) -> list[tuple[str, str, str]]:
    """(uid, email, display name) for every user who should get the update."""
    auth_uids = _get_auth_uids()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for doc in db.collection("users").stream():
        data = doc.to_dict() or {}
        if doc.id not in auth_uids or data.get("notify_enabled") is False:
            continue
        email = resolve_recipient(data)
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append((doc.id, email, data.get("display_name") or ""))
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--send", action="store_true", help="send to every recipient")
    group.add_argument("--to", metavar="EMAIL", help="send one test copy to this address")
    args = parser.parse_args()
    settings = get_settings()

    if args.to:
        await send_announcement_email(args.to, "", settings)
        print(f"Test sent to {args.to}")
        return

    people = recipients(get_db())
    print(f"{len(people)} recipient(s)")
    if not args.send:
        for _, email, name in people:
            print(f"  {email}  {name}")
        print("Dry run. Nothing sent. Add --send to send.")
        return

    sent = failed = 0
    for uid, email, name in people:
        try:
            await send_announcement_email(email, name, settings, uid=uid)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  failed {email}: {exc}")
        await asyncio.sleep(_PAUSE_SECONDS)
    print(f"Sent {sent}, failed {failed}")


if __name__ == "__main__":
    asyncio.run(main())

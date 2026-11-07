"""
Copy Citey's data from Firestore into Postgres (Neon).

Reads every user, with their tracked papers and notifications, from the
Firestore that backend/.env points at, and writes them to the Postgres at
DATABASE_URL_UNPOOLED (else DATABASE_URL). Apply the migrations first
(`uv run alembic upgrade head`).

Safe to run again: everything is upserted, and each user is copied in one
transaction, so a failure leaves earlier users copied and that user
untouched. Firestore is only read.

Run it before the API switches to Postgres, not after: each run refreshes
users' settings from Firestore, which would undo changes made in Postgres
since.

    uv run python scripts/copy_firestore_to_postgres.py --dry-run   # copy, then roll back
    uv run python scripts/copy_firestore_to_postgres.py --only <uid>
    uv run python scripts/copy_firestore_to_postgres.py
"""

import argparse
import asyncio
import sys

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.concurrency import run_blocking
from app.core.db import make_engine
from app.firebase_client import get_db
from app.store.from_firestore import Copied, copy_user


def _read_user(db, uid: str) -> tuple[dict, dict, dict]:
    ref = db.collection("users").document(uid)
    user = ref.get().to_dict() or {}
    tracked = {d.id: d.to_dict() or {} for d in ref.collection("trackedWorks").stream()}
    notifications = {d.id: d.to_dict() or {} for d in ref.collection("notifications").stream()}
    return user, tracked, notifications


async def main(dry_run: bool, only: str | None) -> int:
    settings = get_settings()
    url = settings.database_url_unpooled or settings.database_url
    if not url:
        print("Set DATABASE_URL_UNPOOLED or DATABASE_URL (backend/.env).", file=sys.stderr)
        return 2
    db = get_db()
    uids = [only] if only else sorted(d.id for d in await run_blocking(lambda: list(db.collection("users").list_documents())))
    print(f"{'DRY RUN: ' if dry_run else ''}copying {len(uids)} user(s) from Firestore into Postgres")

    engine = make_engine(url)
    total = Copied(users=0)
    failed: list[str] = []
    for uid in uids:
        user, tracked, notifications = await run_blocking(_read_user, db, uid)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                copied = await copy_user(session, uid, user, tracked, notifications)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                failed.append(uid)
                print(f"  {uid}: FAILED, nothing copied for this user: {exc}", file=sys.stderr)
                continue
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        total.add(copied)
        print(f"  {uid}: {copied.tracked} paper(s), {copied.alerts} new alert(s)")
    await engine.dispose()

    print(f"\n{total.users} user(s), {total.tracked} tracked paper(s), {total.alerts} new alert(s)"
          f"{' (rolled back)' if dry_run else ''}")
    for line in total.skipped:
        print(f"  skipped {line}")
    if failed:
        print(f"{len(failed)} user(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="copy inside a transaction, then roll it back")
    parser.add_argument("--only", metavar="UID", help="copy just this user")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.dry_run, args.only)))

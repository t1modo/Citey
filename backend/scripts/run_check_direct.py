#!/usr/bin/env python3
"""
Run citation check directly (no server) for all users, with full logging.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.firebase_client import get_db
from app.services import email_service
from app.services.citation_service import run_job_for_all_users


async def main() -> None:
    db = get_db()
    print("\nRunning citation check for ALL users (dry_run=False)...\n")
    summary = await run_job_for_all_users(
        db=db,
        email_service=email_service,
        dry_run=False,
    )
    print(f"\nResult: {summary}")


if __name__ == "__main__":
    asyncio.run(main())

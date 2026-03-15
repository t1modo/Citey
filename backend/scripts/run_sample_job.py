#!/usr/bin/env python3
"""
CLI script for testing the citation-check job locally with dry_run=True.

Usage:
    python scripts/run_sample_job.py [DOI]

    DOI  (optional)  The DOI to check. Defaults to "10.1038/nature12345".

Examples:
    python scripts/run_sample_job.py
    python scripts/run_sample_job.py 10.1126/science.abc1234
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so local imports work regardless of
# how the script is invoked.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env *before* importing anything that reads settings.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

import json  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.firebase_client import get_db  # noqa: E402
from app.models import TrackedWork  # noqa: E402
from app.services.citation_service import process_tracked_work  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_doi(doi: str) -> str:
    """Strip common URL prefixes from a DOI string."""
    clean = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if clean.lower().startswith(prefix):
            return clean[len(prefix):]
    return clean


def _doi_to_work_id(doi: str) -> str:
    """Convert a DOI to a safe Firestore document ID."""
    return doi.replace("/", "__")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    settings = get_settings()

    doi = sys.argv[1] if len(sys.argv) > 1 else "10.1038/nature12345"
    doi = _sanitize_doi(doi)
    work_id = _doi_to_work_id(doi)

    logger.info("=" * 60)
    logger.info("Citey — Sample Citation Job (DRY RUN)")
    logger.info("=" * 60)
    logger.info("DOI       : %s", doi)
    logger.info("Work ID   : %s", work_id)
    logger.info("App URL   : %s", settings.app_url)
    logger.info("=" * 60)

    # Build a fake TrackedWork — the real DB is not queried for the work itself.
    fake_work = TrackedWork(
        id=work_id,
        doi=doi,
        openalex_id=None,  # Will be resolved by the service via OpenAlex.
        title=f"[Sample] Work with DOI {doi}",
        authors=[],
        year=None,
        last_checked_at=None,
    )

    logger.info("Initializing Firebase …")
    db = get_db()

    logger.info("Running process_tracked_work with dry_run=True …")
    try:
        count, notifications = await process_tracked_work(
            uid="sample_script_user",
            work=fake_work,
            db=db,
            dry_run=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("process_tracked_work raised an exception: %s", exc, exc_info=True)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Results")
    logger.info("=" * 60)
    logger.info("New citations found : %d", count)

    if notifications:
        for i, notif in enumerate(notifications, start=1):
            print(f"\n  [{i}] Citing paper : {notif.citing_work_title}")
            if notif.citing_work_doi:
                print(f"       DOI         : https://doi.org/{notif.citing_work_doi}")
            elif notif.citing_work_url:
                print(f"       URL         : {notif.citing_work_url}")
            if notif.citing_authors:
                print(f"       Authors     : {', '.join(notif.citing_authors)}")
            if notif.citing_affiliations:
                print(f"       Affiliations: {', '.join(notif.citing_affiliations)}")
            if notif.citing_year:
                print(f"       Year        : {notif.citing_year}")
    else:
        print("\n  No new citations found (or DOI not indexed in OpenAlex).")

    logger.info("=" * 60)
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())

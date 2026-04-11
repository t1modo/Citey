"""
Publication sync service.

Periodically checks each user's linked OpenAlex author profile for new
publications that aren't yet in their trackedWorks collection, and
auto-adds them.

Only OpenAlex-linked authors are synced; S2-only links are skipped because
the S2 works API does not provide a reliable full publication list.
"""

import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from types import ModuleType
from typing import Any

from app.config import Settings
from app.services import openalex as openalex_svc
from app.services.openalex import extract_topics, extract_venue

logger = logging.getLogger(__name__)


def _strip_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.startswith(prefix):
            return doi[len(prefix):]
    return doi


async def sync_new_publications_for_user(
    uid: str,
    user_data: dict,
    db: Any,
    email_service: ModuleType,
    dry_run: bool,
    settings: Settings,
) -> int:
    """
    Diff the user's trackedWorks against their OpenAlex author profile and
    auto-add any publications that are missing.

    Returns the number of works added (0 on dry_run or no new works).
    """
    linked_author_id: str | None = user_data.get("linked_author_id")
    if not linked_author_id:
        return 0

    # Skip S2-only profiles — we can't reliably enumerate all their works.
    if linked_author_id.startswith("S2:"):
        logger.debug("uid=%s linked to S2 author — skipping publication sync.", uid)
        return 0

    logger.info("Publication sync starting for uid=%s author=%s", uid, linked_author_id)

    # Fetch the full publication list from OpenAlex.
    try:
        oa_works = await openalex_svc.get_works_by_author(linked_author_id)
    except Exception as exc:
        logger.error("OpenAlex fetch failed for uid=%s: %s", uid, exc)
        return 0

    if not oa_works:
        logger.info("No works returned from OpenAlex for uid=%s", uid)
        return 0

    # Load the user's existing tracked DOIs (use the doc ID which is doi.replace("/", "__")).
    works_ref = db.collection("users").document(uid).collection("trackedWorks")
    existing_ids: set[str] = {doc.id for doc in works_ref.stream()}

    # Deduplicate near-duplicate titles (arXiv preprint + journal version of same paper).
    # Mirrors the logic in import_works_by_author so sync doesn't add duplicates either.
    def _is_arxiv(doi: str | None) -> bool:
        return bool(doi and doi.lower().startswith("10.48550/arxiv"))

    def _norm_title(title: str) -> str:
        return re.sub(r"[^a-z0-9\s]", "", title.lower()).strip()

    def _is_near_duplicate(a: str, b: str) -> bool:
        return SequenceMatcher(None, a, b).ratio() >= 0.85

    seen_titles: dict[str, dict] = {}
    for raw in oa_works:
        doi = _strip_doi(raw.get("doi"))
        if not doi:
            continue
        doi = doi.lower()
        norm = _norm_title(raw.get("title") or "")
        if not norm:
            continue
        matched_key = next((k for k in seen_titles if _is_near_duplicate(norm, k)), None)
        if matched_key is None:
            seen_titles[norm] = raw
        else:
            stored_doi = _strip_doi(seen_titles[matched_key].get("doi"))
            if _is_arxiv(stored_doi) and not _is_arxiv(doi):
                del seen_titles[matched_key]
                seen_titles[norm] = raw

    now = datetime.now(tz=timezone.utc)
    added_titles: list[str] = []

    for raw in seen_titles.values():
        doi = _strip_doi(raw.get("doi"))
        if not doi:
            continue  # Can't track a work with no DOI.
        doi = doi.lower()

        work_id = doi.replace("/", "__")
        if work_id in existing_ids:
            continue  # Already tracked.

        title: str = raw.get("title") or "Untitled"
        authors: list[str] = [
            a.get("author", {}).get("display_name", "").strip()
            for a in raw.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        year: int | None = raw.get("publication_year")
        openalex_id: str | None = raw.get("id")
        openalex_citation_count: int | None = raw.get("cited_by_count")

        if not dry_run:
            works_ref.document(work_id).set({
                "doi": doi,
                "openalex_id": openalex_id,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": extract_venue(raw),
                "work_type": raw.get("type"),
                "topics": extract_topics(raw),
                "added_at": now,
                "last_checked_at": None,
                "openalex_citation_count": openalex_citation_count,
            })
            existing_ids.add(work_id)

        added_titles.append(title)
        logger.info("Auto-added new publication '%s' (doi=%s) for uid=%s", title, doi, uid)

    count = len(added_titles)
    if count == 0:
        logger.info("Publication sync complete for uid=%s — no new works.", uid)
        return 0

    logger.info("Publication sync complete for uid=%s — added %d work(s).", uid, count)

    if dry_run:
        return count

    # Record sync timestamp on the user document.
    db.collection("users").document(uid).set(
        {"last_publication_sync": now}, merge=True
    )

    # Send email notification if the user has opted in.
    notify_pubs = user_data.get("notify_new_publications", True)
    notify_global = user_data.get("notify_enabled", True)
    if notify_pubs and notify_global:
        to_email: str | None = user_data.get("notification_email") or user_data.get("email")
        if to_email:
            recipient_name: str = user_data.get("display_name") or to_email
            try:
                await email_service.send_new_publications_email(
                    to_email=to_email,
                    recipient_name=recipient_name,
                    new_titles=added_titles,
                    settings=settings,
                )
            except Exception as exc:
                logger.error(
                    "Failed to send new-publications email to %s: %s", to_email, exc
                )

    return count


async def sync_new_publications_for_all_users(
    db: Any,
    email_service: ModuleType,
    dry_run: bool,
    settings: Settings,
) -> dict:
    """
    Run publication sync for every user that has a linked author.
    Returns a summary dict.
    """
    users_processed = 0
    total_added = 0

    for user_doc in db.collection("users").stream():
        data: dict = user_doc.to_dict() or {}
        if not data.get("linked_author_id"):
            continue
        uid: str = user_doc.id
        try:
            added = await sync_new_publications_for_user(
                uid=uid,
                user_data=data,
                db=db,
                email_service=email_service,
                dry_run=dry_run,
                settings=settings,
            )
            total_added += added
            users_processed += 1
        except Exception as exc:
            logger.error("Publication sync failed for uid=%s: %s", uid, exc, exc_info=True)

    return {
        "users_processed": users_processed,
        "works_added": total_added,
    }

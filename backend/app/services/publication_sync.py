"""
Publication sync service.

Periodically checks each user's linked OpenAlex author profile for new
publications that aren't yet in their trackedWorks collection, and
auto-adds them.

Only OpenAlex-linked authors are synced; S2-only links are skipped because
the S2 works API does not provide a reliable full publication list.
"""

import logging
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

from app.config import Settings
from app.services import openalex as openalex_svc
from app.services.openalex import extract_topics, extract_venue

from app.services.email_service import resolve_recipient
from app.services.normalize import dedupe_works_by_title, doi_to_work_id, normalize_doi

logger = logging.getLogger(__name__)




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
    # Compare case-insensitively: older imports stored mixed-case DOI IDs.
    existing_ids: set[str] = {doc.id.lower() for doc in works_ref.stream()}
    # Works the user deleted on purpose must not be re-added by the sync.
    dismissed: set[str] = {d.lower() for d in (user_data.get("dismissed_work_ids") or [])}

    now = datetime.now(tz=timezone.utc)
    added_titles: list[str] = []

    for raw in dedupe_works_by_title(oa_works):
        doi = normalize_doi(raw.get("doi"))
        if not doi:
            continue  # Can't track a work with no DOI.

        work_id = doi_to_work_id(doi)
        if work_id in dismissed:
            continue
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
        to_email: str | None = resolve_recipient(user_data)
        if to_email:
            recipient_name: str = user_data.get("display_name") or to_email
            try:
                await email_service.send_new_publications_email(
                    to_email=to_email,
                    recipient_name=recipient_name,
                    new_titles=added_titles,
                    settings=settings,
                    uid=uid,
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

    from app.services.citation_service import _get_auth_uids
    auth_uids = _get_auth_uids()
    for user_doc in db.collection("users").stream():
        uid: str = user_doc.id
        if uid not in auth_uids:
            logger.warning("Skipping orphaned Firestore user uid=%s in publication sync", uid)
            continue
        data: dict = user_doc.to_dict() or {}
        if not data.get("linked_author_id"):
            continue
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

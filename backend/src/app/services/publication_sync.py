"""
Publication sync service.

Periodically checks each user's linked OpenAlex author profile for new
publications they don't track yet, and adds them.

Only OpenAlex-linked authors are synced; S2-only links are skipped because
the S2 works API does not provide a reliable full publication list.
"""

import logging
import time
from datetime import datetime, timezone
from types import ModuleType

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.services import openalex as openalex_svc
from app.services.openalex import extract_topics, extract_venue

from app.services.email_service import resolve_recipient
from app.services.normalize import dedupe_works_by_title, doi_to_work_id, normalize_doi
from app.services import convert, tracking_service
from app.store import UserStore, WorkStore

logger = logging.getLogger(__name__)




async def sync_new_publications_for_user(
    uid: str,
    session: AsyncSession,
    email_service: ModuleType,
    dry_run: bool,
    settings: Settings,
    user_data: dict | None = None,
) -> int:
    """
    Diff the papers the user tracks against their OpenAlex author profile
    and add any publications that are missing. *user_data* (the user as
    convert.user_data gives it) is read from the database when not given.

    Returns the number of works added (or, in a dry run, that would be).
    """
    if user_data is None:
        user = await UserStore(session).get(uid)
        if user is None:
            return 0
        user_data = convert.user_data(user)
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

    # The papers already tracked, by key (doi with "/" replaced), compared
    # case-insensitively: older imports stored mixed-case keys.
    existing_ids: set[str] = await WorkStore(session).tracked_keys(uid)
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
            await tracking_service.track_paper(session, uid, work_id, {
                "doi": doi,
                "openalex_id": openalex_id,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": extract_venue(raw),
                "work_type": raw.get("type"),
                "topics": extract_topics(raw),
                "openalex_citation_count": openalex_citation_count,
            }, now=now)
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

    # Record the sync time, and keep the new papers even if the email fails.
    await UserStore(session).update_fields(uid, last_publication_sync_at=now)
    await session.commit()

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
    session: AsyncSession,
    email_service: ModuleType,
    dry_run: bool,
    settings: Settings,
    cursor: str | None = None,
    time_budget_seconds: float | None = None,
) -> dict:
    """
    Run publication sync for every user that has a linked author, in uid
    order. *cursor* and *time_budget_seconds* batch the run the same way as
    run_job_for_all_users.

    Returns {users_processed, works_added, next_cursor}; next_cursor is None
    when every user is done.
    """
    from app.services.citation_service import _get_auth_uids, out_of_time

    users_processed = 0
    total_added = 0
    started = time.monotonic()
    next_cursor: str | None = None
    last_done: str | None = cursor

    auth_uids = await _get_auth_uids()
    users = UserStore(session)
    for uid in await users.ids_after(cursor):
        if out_of_time(started, time_budget_seconds):
            next_cursor = last_done
            break
        last_done = uid
        if uid not in auth_uids:
            logger.warning("Skipping user uid=%s with no sign-in account in publication sync", uid)
            continue
        user = await users.get(uid)
        data: dict = convert.user_data(user) if user else {}
        if not data.get("linked_author_id"):
            continue
        try:
            added = await sync_new_publications_for_user(
                uid=uid,
                user_data=data,
                session=session,
                email_service=email_service,
                dry_run=dry_run,
                settings=settings,
            )
            total_added += added
            users_processed += 1
        except Exception as exc:
            await session.rollback()
            logger.error("Publication sync failed for uid=%s: %s", uid, exc, exc_info=True)

    return {
        "users_processed": users_processed,
        "works_added": total_added,
        "next_cursor": next_cursor,
    }

"""
Citation-checking orchestration service.

This module is responsible for:
1. Iterating a user's tracked works.
2. Querying OpenAlex for new citing papers since the last check.
3. Writing Notification documents to Firestore (deduplication via doc ID).
4. Triggering email delivery for users who have notifications enabled.
"""

import asyncio
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any

from firebase_admin import auth as firebase_auth

from app.models import Notification, TrackedWork
from app.services import openalex as openalex_svc
from app.services import semantic_scholar as s2_svc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-work processing
# ---------------------------------------------------------------------------


async def process_tracked_work(
    uid: str,
    work: TrackedWork,
    db: Any,
    dry_run: bool = False,
) -> tuple[int, list[Notification]]:
    """
    Check for new citations of *work* and write Notification documents.

    Returns (new_notification_count, list_of_new_notification_objects).
    """
    # 1. Resolve the OpenAlex work ID — only DOI/OpenAlex ID are used; no
    #    pre-supplied metadata is sent to the API.
    openalex_id: str | None = work.openalex_id
    if not openalex_id and work.doi:
        logger.info(
            "No cached OpenAlex ID for work %s — resolving from doi=%s (uid=%s)",
            work.id, work.doi, uid,
        )
        raw = await openalex_svc.get_work_by_doi(work.doi)
        if raw:
            openalex_id = raw.get("id")
            logger.info("Resolved OpenAlex ID: %s for work %s", openalex_id, work.id)
            if not dry_run and openalex_id:
                (
                    db.collection("users")
                    .document(uid)
                    .collection("trackedWorks")
                    .document(work.id)
                    .update({"openalex_id": openalex_id})
                )
        else:
            logger.warning(
                "OpenAlex returned no result for doi=%s (work %s, uid=%s)",
                work.doi, work.id, uid,
            )

    if not openalex_id and not work.doi:
        logger.warning(
            "No OpenAlex ID or DOI for work %s (uid=%s) — skipping.", work.id, uid
        )
        return 0, []

    if not openalex_id:
        logger.info(
            "OpenAlex ID unavailable for work %s (uid=%s) — will rely on Semantic Scholar.",
            work.id, uid,
        )

    logger.info(
        "Fetching citations for work %s (openalex_id=%s, doi=%s, uid=%s)",
        work.id, openalex_id, work.doi, uid,
    )

    # 2. Fetch from OpenAlex and Semantic Scholar in parallel.
    #    Only citing papers published within the last 30 days are considered.
    #    The date filter is applied as early as possible:
    #      - OpenAlex: passed as a server-side filter to avoid fetching stale pages.
    #      - S2: applied after raw fetch but before expensive affiliation enrichment.
    #    A final post-normalization filter acts as a strict backstop.
    thirty_days_ago: str = (
        datetime.now(tz=timezone.utc) - timedelta(days=30)
    ).strftime("%Y-%m-%d")

    async def _empty() -> list:
        return []

    oa_task = (
        openalex_svc.get_citing_works(openalex_id, since_date=thirty_days_ago)
        if openalex_id
        else _empty()
    )
    s2_task = (
        s2_svc.get_citing_papers(work.doi, since_date=thirty_days_ago)
        if work.doi
        else _empty()
    )

    oa_results, s2_results = await asyncio.gather(oa_task, s2_task, return_exceptions=True)

    if isinstance(oa_results, Exception):
        logger.warning("OpenAlex citation fetch failed for work %s: %s", work.id, oa_results)
        oa_results = []
    if isinstance(s2_results, Exception):
        logger.warning("S2 citation fetch failed for work %s: %s", work.id, s2_results)
        s2_results = []

    logger.info(
        "OpenAlex: %d citing work(s) | S2: %d citing work(s) for %s (uid=%s)",
        len(oa_results), len(s2_results), work.id, uid,
    )

    # 4. Normalise both source lists to the same dict shape, then merge.
    #    OpenAlex results take priority (richer metadata: affiliations, etc.).
    #    A paper present in both is kept only once, keyed by DOI then title.
    oa_normalized = [openalex_svc.normalize_citing_work(r) for r in oa_results]
    s2_normalized = [s2_svc.normalize_citing_work(r) for r in s2_results]

    merged: dict[str, dict] = {}
    for n in oa_normalized:
        key = _dedup_key(n)
        if key:
            merged[key] = n
    for n in s2_normalized:
        key = _dedup_key(n)
        if key and key not in merged:
            merged[key] = n

    all_normalized = list(merged.values())

    # 30-day backstop.
    # Prefer publication_date for precise filtering.  When it's absent (common
    # for papers that have been indexed but not yet dated by OA/S2), fall back
    # to year: accept anything from the cutoff year or later so that recently
    # published papers don't get silently dropped on the first job run and only
    # appear once the API retroactively assigns a date.
    before_date_filter = len(all_normalized)
    cutoff_year = int(thirty_days_ago[:4])
    all_normalized = [
        n for n in all_normalized
        if (n.get("publication_date") or "") >= thirty_days_ago
        or (not n.get("publication_date") and (n.get("year") or 0) >= cutoff_year)
    ]
    date_filtered_count = before_date_filter - len(all_normalized)

    logger.info(
        "Merged citing works for %s (uid=%s): %d unique after dedup "
        "(%d OA + %d S2 before merge); %d dropped by 30-day date filter",
        work.id, uid, len(all_normalized), len(oa_normalized), len(s2_normalized),
        date_filtered_count,
    )

    notifications_ref = db.collection("users").document(uid).collection("notifications")

    # 5+6. Single Firestore pass: read all existing notifications for this work.
    #
    #  Fresh add (last_checked_at is None):
    #    Any notifications are stale leftovers from a failed cascade-delete.
    #    Delete them all so existing_ids stays empty.
    #
    #  Normal check:
    #    Build existing_ids using the CANONICAL doc ID (DOI-keyed when a
    #    citing_work_doi is available).  Old notifications stored with an
    #    OpenAlex-URL-based doc ID are silently migrated to the DOI-keyed
    #    format in the same pass, so they don't block new writes.
    existing_ids: set[str] = set()
    is_fresh_add = work.last_checked_at is None

    if not dry_run:
        stale_refs = []
        for ndoc in notifications_ref.where("cited_work_id", "==", work.id).stream():
            if is_fresh_add:
                stale_refs.append(ndoc.reference)
            else:
                data = ndoc.to_dict() or {}
                citing_doi_stored = data.get("citing_work_doi") or ""
                # Canonical ID: DOI-keyed if possible, otherwise keep as-is.
                canonical_id = (
                    f"{work.id}__{_safe_doc_id(citing_doi_stored)}"
                    if citing_doi_stored
                    else ndoc.id
                )
                if canonical_id != ndoc.id:
                    # Legacy OA-ID-keyed doc — migrate to DOI-keyed.
                    notifications_ref.document(canonical_id).set(data)
                    ndoc.reference.delete()
                    logger.info(
                        "Migrated notification %s → %s (uid=%s)",
                        ndoc.id, canonical_id, uid,
                    )
                existing_ids.add(canonical_id)

        if stale_refs:
            for ref in stale_refs:
                ref.delete()
            logger.warning(
                "Wiped %d stale notification(s) for freshly-added work %s (uid=%s).",
                len(stale_refs), work.id, uid,
            )

        logger.info(
            "%d existing notification(s) on record for work %s (uid=%s).",
            len(existing_ids), work.id, uid,
        )

    new_count = 0
    skipped_count = 0
    new_notifications: list[Notification] = []

    for normalized in all_normalized:
        # Prefer DOI as the stable cross-source identifier; fall back to
        # source-specific ID (OpenAlex W-id or S2 paper ID).
        # Lowercase the DOI for a consistent doc ID — DOIs are case-insensitive
        # and mixed-case variants from different sources would otherwise create
        # duplicate notification documents for the same citing paper.
        citing_doi: str = (normalized.get("doi") or "").lower()
        citing_id: str = citing_doi or normalized["id"] or ""
        if not citing_id:
            logger.debug("Skipping citing work with no usable ID: %s", normalized.get("title"))
            continue

        doc_id = f"{work.id}__{_safe_doc_id(citing_id)}"

        if not dry_run:
            if doc_id in existing_ids:
                logger.debug("Notification %s already exists — skipping.", doc_id)
                skipped_count += 1
                continue
        else:
            logger.info(
                "[DRY RUN] Would write notification %s: '%s' cites '%s'",
                doc_id, normalized["title"], work.title,
            )

        now = datetime.now(tz=timezone.utc)
        notification = Notification(
            id=doc_id,
            cited_work_id=work.id,
            cited_work_title=work.title,
            citing_work_id=citing_id,
            citing_work_title=_truncate(normalized["title"], _TITLE_MAX_CHARS),
            citing_work_doi=citing_doi or None,
            citing_work_url=normalized.get("url"),
            citing_authors=[
                _truncate(a, _AUTHOR_NAME_MAX_CHARS)
                for a in normalized.get("authors", [])
            ],
            citing_affiliations=normalized.get("affiliations", []),
            citing_year=normalized.get("year"),
            citing_publication_date=normalized.get("publication_date"),
            seen=False,
            created_at=now,
        )

        if not dry_run:
            doc_data = notification.model_dump()
            doc_data["created_at"] = now
            notifications_ref.document(doc_id).set(doc_data)
            logger.info("Wrote notification %s for uid=%s", doc_id, uid)

        new_count += 1
        new_notifications.append(notification)

    logger.info(
        "Work %s (uid=%s): %d new notification(s), %d duplicate(s) skipped "
        "out of %d unique citing work(s).",
        work.id, uid, new_count, skipped_count, len(all_normalized),
    )

    # 7. Update last_checked_at on the tracked work.
    if not dry_run:
        (
            db.collection("users")
            .document(uid)
            .collection("trackedWorks")
            .document(work.id)
            .update({"last_checked_at": datetime.now(tz=timezone.utc)})
        )

    return new_count, new_notifications


# ---------------------------------------------------------------------------
# Full-user-sweep job
# ---------------------------------------------------------------------------


async def run_job_for_user(
    uid: str,
    user_data: dict,
    db: Any,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
) -> tuple[int, int]:
    """
    Run citation checks for all tracked works belonging to a single user.

    Returns (works_processed, new_notifications).
    """
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    logger.info("Processing user uid=%s", uid)

    works_docs = (
        db.collection("users").document(uid).collection("trackedWorks").stream()
    )
    works: list[TrackedWork] = []
    for wdoc in works_docs:
        wdata = wdoc.to_dict() or {}
        works.append(_doc_to_tracked_work(wdoc.id, wdata))

    user_new_notifications: list[Notification] = []
    works_processed = 0

    for work in works:
        works_processed += 1
        try:
            count, notifications = await process_tracked_work(
                uid=uid, work=work, db=db, dry_run=dry_run
            )
            user_new_notifications.extend(notifications)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error processing work %s for uid=%s: %s", work.id, uid, exc,
                exc_info=True,
            )

    # Fetch Semantic Scholar citation counts for all works in one batch.
    if not dry_run:
        try:
            from app.services.semantic_scholar import get_citation_counts

            dois = [w.doi for w in works if w.doi]
            if dois:
                s2_counts = await get_citation_counts(dois)
                works_ref = db.collection("users").document(uid).collection("trackedWorks")
                for work in works:
                    if not work.doi:
                        continue
                    s2_count = s2_counts.get(work.doi.lower())
                    if s2_count is not None:
                        works_ref.document(work.id).update({"s2_citation_count": s2_count})
                logger.info(
                    "Updated S2 citation counts for uid=%s (%d works matched)",
                    uid, len(s2_counts),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch S2 citation counts for uid=%s: %s", uid, exc)

    # Fetch OpenAlex citation counts (cited_by_count) for all works in one batch.
    if not dry_run:
        try:
            oa_ids = [w.openalex_id for w in works if w.openalex_id]
            if oa_ids:
                oa_counts = await openalex_svc.get_citation_counts(oa_ids)
                works_ref = db.collection("users").document(uid).collection("trackedWorks")
                for work in works:
                    if not work.openalex_id:
                        continue
                    short_id = (
                        work.openalex_id[len("https://openalex.org/"):]
                        if work.openalex_id.startswith("https://openalex.org/")
                        else work.openalex_id
                    )
                    oa_count = oa_counts.get(short_id)
                    if oa_count is not None:
                        works_ref.document(work.id).update({"openalex_citation_count": oa_count})
                logger.info(
                    "Updated OpenAlex citation counts for uid=%s (%d works matched)",
                    uid, len(oa_counts),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch OpenAlex citation counts for uid=%s: %s", uid, exc)

    # Send an immediate email when new citations are found.
    to_email: str | None = user_data.get("notification_email") or user_data.get("email")
    notify_enabled: bool = user_data.get("notify_enabled", True)

    email_verified = True
    try:
        user_record = firebase_auth.get_user(uid)
        email_verified = user_record.email_verified
    except Exception as exc:
        logger.warning("Could not check email_verified for uid=%s: %s", uid, exc)

    if user_new_notifications and to_email and not email_verified:
        logger.info("Skipping citation email — uid=%s email not verified.", uid)

    if user_new_notifications and to_email and notify_enabled and email_verified:
        if dry_run:
            logger.info(
                "[DRY RUN] Would email %s with %d new citation(s).",
                to_email, len(user_new_notifications),
            )
        else:
            try:
                citation_groups = _group_notifications(user_new_notifications)
                recipient_name: str = user_data.get("display_name") or to_email
                await email_service.send_digest_email(
                    to_email=to_email,
                    recipient_name=recipient_name,
                    citation_groups=citation_groups,
                    total_citations=len(user_new_notifications),
                    digest_date=datetime.now(tz=timezone.utc),
                    settings=settings,
                    uid=uid,
                )
                logger.info(
                    "Citation email sent to %s (uid=%s): %d new citation(s) across %d paper(s).",
                    to_email, uid, len(user_new_notifications), len(citation_groups),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to send citation email to %s (uid=%s): %s",
                    to_email, uid, exc, exc_info=True,
                )

    return works_processed, len(user_new_notifications)


async def run_job_for_all_users(
    db: Any,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
) -> dict[str, int]:
    """
    Iterate every user in Firestore and run citation checks for all their
    tracked works.

    Returns a summary dict:
        {users_processed, works_processed, new_notifications}
    """
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    users_processed = 0
    works_processed = 0
    total_new_notifications = 0

    for user_doc in db.collection("users").stream():
        uid: str = user_doc.id
        user_data: dict = user_doc.to_dict() or {}
        users_processed += 1

        wp, nn = await run_job_for_user(
            uid=uid,
            user_data=user_data,
            db=db,
            email_service=email_service,
            dry_run=dry_run,
            settings=settings,
        )
        works_processed += wp
        total_new_notifications += nn

    summary = {
        "users_processed": users_processed,
        "works_processed": works_processed,
        "new_notifications": total_new_notifications,
    }
    logger.info("Job complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Notification cleanup
# ---------------------------------------------------------------------------

_NOTIFICATION_TTL_DAYS = 30


async def prune_user_notifications(
    uid: str, db: Any, dry_run: bool = False
) -> int:
    """
    Delete stale notification documents for a single user.

    A notification is stale if EITHER:
    - its ``created_at`` is older than ``_NOTIFICATION_TTL_DAYS`` days, OR
    - its ``citing_publication_date`` is set and older than ``_NOTIFICATION_TTL_DAYS`` days.

    The two criteria are merged so each document is only deleted once.
    Returns the number of notifications deleted (or that would be deleted in
    dry-run mode).
    """
    cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=_NOTIFICATION_TTL_DAYS)
    cutoff_date_str = cutoff_dt.strftime("%Y-%m-%d")

    notifs_ref = db.collection("users").document(uid).collection("notifications")

    # Gather unique doc references to delete (merge both criteria).
    to_delete: dict[str, Any] = {}

    # 1. Stale by creation time (catches notifications without a publication date).
    for doc in notifs_ref.where("created_at", "<", cutoff_dt).stream():
        to_delete[doc.id] = doc.reference

    # 2. Stale by citing paper's publication date.  Firestore range queries on a
    #    string field only match documents where the field *exists*, so this won't
    #    accidentally catch notifications that have no publication date stored.
    for doc in notifs_ref.where("citing_publication_date", "<", cutoff_date_str).stream():
        to_delete[doc.id] = doc.reference

    count = len(to_delete)

    if count:
        action = "[DRY RUN] would delete" if dry_run else "deleted"
        logger.info(
            "Prune uid=%s: %s %d notification(s) older than %d days.",
            uid, action, count, _NOTIFICATION_TTL_DAYS,
        )

    if count and not dry_run:
        # Firestore batch is capped at 500 writes — chunk if needed.
        refs = list(to_delete.values())
        for i in range(0, len(refs), 500):
            batch = db.batch()
            for ref in refs[i : i + 500]:
                batch.delete(ref)
            batch.commit()

    return count


async def cleanup_old_notifications(db: Any, dry_run: bool = False) -> dict:
    """
    Delete stale notification documents across all users.

    Returns a summary dict: {users_processed, notifications_deleted}.
    """
    users_processed = 0
    total_deleted = 0

    for user_doc in db.collection("users").stream():
        uid: str = user_doc.id
        users_processed += 1
        count = await prune_user_notifications(uid, db, dry_run)
        total_deleted += count

    summary = {"users_processed": users_processed, "notifications_deleted": total_deleted}
    logger.info("Notification cleanup complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_notifications(notifications: list[Notification]) -> list[dict]:
    """
    Group a flat list of Notifications by cited paper.

    Returns a list of dicts, each with:
        cited_work_title, cited_work_doi, citations (list[Notification])
    """
    groups: dict[str, dict] = {}
    for n in notifications:
        key = n.cited_work_id
        if key not in groups:
            doi_guess = key.replace("__", "/")
            groups[key] = {
                "cited_work_title": n.cited_work_title or key,
                "cited_work_doi": doi_guess if "/" in doi_guess else None,
                "citations": [],
            }
        groups[key]["citations"].append(n)
    return list(groups.values())


_TITLE_MAX_CHARS = 300
_AUTHOR_NAME_MAX_CHARS = 100


def _truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* characters, appending '…' if shortened."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _safe_doc_id(value: str) -> str:
    """Replace characters that are invalid in Firestore document IDs."""
    return value.replace("/", "__").replace(".", "_")


def _normalize_title(title: str) -> str:
    """
    Lowercase and normalize a title for fuzzy dedup.

    - NFKD decomposition maps accented characters to their ASCII base form
      (e.g. 'résumé' → 'resume') so encoding differences between sources
      don't produce false misses.
    - Non-ASCII word characters (CJK, Arabic, etc.) are preserved so that
      titles composed entirely of non-ASCII text still produce a usable key
      instead of collapsing to an empty string.
    - All punctuation, symbols, and whitespace are stripped.
    """
    nfkd = unicodedata.normalize("NFKD", title.lower())
    no_combining = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^\w]", "", no_combining, flags=re.UNICODE)


def _dedup_key(normalized: dict) -> str:
    """
    Return a stable dedup key for a normalized citing-work dict.
    Prefers DOI (exact, cross-source stable); falls back to normalized title.
    """
    doi = (normalized.get("doi") or "").lower().strip()
    if doi:
        return f"doi:{doi}"
    title = normalized.get("title") or ""
    nt = _normalize_title(title)
    return f"title:{nt}" if nt else ""


def _doc_to_tracked_work(doc_id: str, data: dict) -> TrackedWork:
    """Convert a Firestore document dict to a TrackedWork model."""

    def _to_dt(val: Any) -> datetime | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if hasattr(val, "timestamp"):
            return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
        return None

    return TrackedWork(
        id=doc_id,
        doi=data.get("doi"),
        openalex_id=data.get("openalex_id"),
        title=data.get("title", ""),
        authors=data.get("authors", []),
        year=data.get("year"),
        venue=data.get("venue"),
        work_type=data.get("work_type"),
        topics=data.get("topics", []),
        added_at=_to_dt(data.get("added_at")),
        last_checked_at=_to_dt(data.get("last_checked_at")),
        s2_citation_count=data.get("s2_citation_count"),
        openalex_citation_count=data.get("openalex_citation_count"),
    )


# ---------------------------------------------------------------------------
# Daily digest email
# ---------------------------------------------------------------------------


def _firestore_dt(val: Any) -> datetime | None:
    """Coerce a Firestore timestamp or ISO string to an aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if hasattr(val, "timestamp"):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def send_daily_digest_for_all_users(
    db: Any,
    email_service: ModuleType,
    settings: Any = None,
) -> dict[str, int]:
    """
    Send one digest email per user containing all notifications created in the
    past 24 hours.  Citations are grouped by the user's cited paper so the
    email is easy to scan.

    Returns a summary dict: {users_emailed, total_citations_sent}.
    """
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    users_emailed = 0
    total_citations_sent = 0

    for user_doc in db.collection("users").stream():
        uid: str = user_doc.id
        user_data: dict = user_doc.to_dict() or {}

        notify_enabled: bool = user_data.get("notify_enabled", True)
        to_email: str | None = user_data.get("notification_email") or user_data.get("email")
        if not notify_enabled or not to_email:
            continue

        try:
            user_record = firebase_auth.get_user(uid)
            if not user_record.email_verified:
                logger.info("Skipping digest — uid=%s email not verified.", uid)
                continue
        except Exception as exc:
            logger.warning("Could not check email_verified for uid=%s: %s", uid, exc)

        # Collect notifications created in the last 24 hours.
        recent: list[Notification] = []
        notifs_ref = db.collection("users").document(uid).collection("notifications")
        for ndoc in notifs_ref.stream():
            ndata = ndoc.to_dict() or {}
            created_at = _firestore_dt(ndata.get("created_at"))
            if created_at and created_at >= cutoff:
                recent.append(
                    Notification(
                        id=ndoc.id,
                        cited_work_id=ndata.get("cited_work_id", ""),
                        cited_work_title=ndata.get("cited_work_title", ""),
                        citing_work_id=ndata.get("citing_work_id", ""),
                        citing_work_title=ndata.get("citing_work_title", ""),
                        citing_work_doi=ndata.get("citing_work_doi"),
                        citing_work_url=ndata.get("citing_work_url"),
                        citing_authors=ndata.get("citing_authors", []),
                        citing_affiliations=ndata.get("citing_affiliations", []),
                        citing_year=ndata.get("citing_year"),
                        citing_publication_date=ndata.get("citing_publication_date"),
                        seen=ndata.get("seen", False),
                        created_at=created_at,
                    )
                )

        if not recent:
            continue

        citation_groups = _group_notifications(recent)
        # Sort each group's citations newest-first.
        for g in citation_groups:
            g["citations"].sort(
                key=lambda n: n.created_at or datetime(1970, 1, 1, tzinfo=timezone.utc),
                reverse=True,
            )
        recipient_name: str = user_data.get("display_name") or to_email

        try:
            await email_service.send_digest_email(
                to_email=to_email,
                recipient_name=recipient_name,
                citation_groups=citation_groups,
                total_citations=len(recent),
                digest_date=datetime.now(tz=timezone.utc),
                settings=settings,
                uid=uid,
            )
            users_emailed += 1
            total_citations_sent += len(recent)
            logger.info(
                "Digest sent to %s (uid=%s): %d citation(s) across %d paper(s)",
                to_email, uid, len(recent), len(citation_groups),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send digest to %s (uid=%s): %s", to_email, uid, exc,
                exc_info=True,
            )

    summary = {"users_emailed": users_emailed, "total_citations_sent": total_citations_sent}
    logger.info("Daily digest complete: %s", summary)
    return summary

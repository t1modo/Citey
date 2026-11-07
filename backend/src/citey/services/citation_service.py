"""
Citation-checking orchestration service.

This module is responsible for:
1. Iterating a user's tracked works.
2. Querying OpenAlex, Semantic Scholar, OpenCitations and Europe PMC for
   new citing papers since the last check.
3. Writing Notification documents to Firestore (deduplication via doc ID).
4. Triggering email delivery for users who have notifications enabled.
"""

import asyncio
import logging
import threading
import time
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any

from firebase_admin import auth as firebase_auth

from citey.models import Notification, TrackedWork, is_openalex_work_id
from citey.services.citing_identity import is_junk, keys_for_normalized, merge_records
from citey.services import crossref as crossref_svc
from citey.services import europe_pmc as europe_pmc_svc
from citey.services import openalex as openalex_svc
from citey.services import opencitations as opencitations_svc
from citey.services import semantic_scholar as s2_svc

from citey.services.email_service import resolve_recipient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-work processing
# ---------------------------------------------------------------------------


async def process_tracked_work(
    uid: str,
    work: TrackedWork,
    db: Any,
    dry_run: bool = False,
    notified_ids: set[str] | None = None,
    source_failures: list[str] | None = None,
    notified_keys: set[str] | None = None,
    baseline_done: bool = False,
) -> tuple[int, list[Notification]]:
    """
    Check for new citations of *work* and write Notification documents.

    *notified_ids* is the work's permanent record of notification doc IDs
    already sent (``notified_ids`` on the trackedWorks doc). Notifications
    themselves are pruned after 30 days, so without this record a citing
    paper that still passes the date filter (e.g. one with only a year)
    would be re-notified every month.

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
            # Let the caller's count refresh use the resolved ID this run.
            work.openalex_id = openalex_id
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

    # 2. Fetch from every source in parallel.
    #    Indexes can take weeks to list a new paper, so "new" means "not
    #    reported before" (any identity key in notified_keys), not "published
    #    in the last 30 days". Citing papers from the past year are considered.
    now = datetime.now(tz=timezone.utc)
    window_start = (now - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    recent_start = (now - timedelta(days=_RECENT_DAYS)).strftime("%Y-%m-%d")
    is_fresh_add = work.last_checked_at is None
    known_keys: set[str] = set(notified_keys or ())
    # The first complete check of a work (or of a work tracked before the
    # wider window existed) records older citations silently instead of
    # emailing a year of them at once.
    baseline = not baseline_done

    async def _empty() -> list:
        return []

    oa_task = (
        openalex_svc.get_citing_works(openalex_id, since_date=window_start)
        if openalex_id
        else _empty()
    )
    s2_task = (
        s2_svc.get_citing_papers(
            work.doi,
            since_date=window_start,
            known_keys=known_keys,
            enrich_since=recent_start if baseline else None,
        )
        if work.doi
        else _empty()
    )

    oc_task = (
        opencitations_svc.get_citing_refs(work.doi, since_date=window_start)
        if work.doi
        else _empty()
    )
    epmc_task = (
        europe_pmc_svc.get_citing_works(work.doi, since_date=window_start)
        if work.doi
        else _empty()
    )

    oa_results, s2_results, oc_refs, epmc_results = await asyncio.gather(
        oa_task, s2_task, oc_task, epmc_task, return_exceptions=True
    )

    # A source that failed is recorded as failed, never as "no citations".
    attempted = (["openalex"] if openalex_id else []) + (
        ["semantic_scholar", "opencitations", "europe_pmc"] if work.doi else []
    )
    failed: list[str] = []
    if isinstance(oa_results, BaseException):
        logger.warning("OpenAlex citation fetch failed for work %s: %s", work.id, oa_results)
        failed.append("openalex")
        oa_results = []
    if isinstance(s2_results, BaseException):
        logger.warning("S2 citation fetch failed for work %s: %s", work.id, s2_results)
        failed.append("semantic_scholar")
        s2_results = []
    if isinstance(oc_refs, BaseException):
        logger.warning("OpenCitations fetch failed for work %s: %s", work.id, oc_refs)
        failed.append("opencitations")
        oc_refs = []
    if isinstance(epmc_results, BaseException):
        logger.warning("Europe PMC fetch failed for work %s: %s", work.id, epmc_results)
        failed.append("europe_pmc")
        epmc_results = []

    logger.info(
        "OpenAlex: %d | S2: %d | OpenCitations: %d | Europe PMC: %d citing record(s) for %s (uid=%s)",
        len(oa_results), len(s2_results), len(oc_refs), len(epmc_results), work.id, uid,
    )

    # 3. Normalise, drop notices (errata, retractions), and merge every record
    #    of the same paper across sources and versions. OpenAlex comes first,
    #    so its richer metadata wins; the others fill gaps.
    normalized = [openalex_svc.normalize_citing_work(r) for r in oa_results]
    normalized += [s2_svc.normalize_citing_work(r) for r in s2_results]
    epmc_normalized = [europe_pmc_svc.normalize_citing_work(r) for r in epmc_results]
    hydrated, hydrate_failed = await _hydrate_extra_citations(
        oc_refs, epmc_normalized, normalized, known_keys, work.id
    )
    if hydrate_failed and "opencitations" not in failed:
        # Citing papers were found but could not be described; the baseline
        # must not finish, or they would surface later as new.
        failed.append("opencitations")
    normalized += hydrated + epmc_normalized
    if source_failures is not None:
        source_failures.extend(failed)
    # OpenCitations and Europe PMC only add to the two main sources; with
    # both main sources down the work does not count as checked.
    primary = [src for src in attempted if src in ("openalex", "semantic_scholar")]
    all_sources_failed = bool(primary) and all(src in failed for src in primary)
    candidates = [n for n in normalized if not is_junk(n.get("title"), n.get("type"))]
    junk_count = len(normalized) - len(candidates)
    merged = [n for n in merge_records(candidates) if _published_since(n, window_start)]

    logger.info(
        "Citing works for %s (uid=%s): %d unique of %d records; %d notice(s) dropped; baseline=%s",
        work.id, uid, len(merged), len(normalized), junk_count, baseline,
    )

    notifications_ref = db.collection("users").document(uid).collection("notifications")

    # 4. Existing notification documents for this work. On a fresh add they
    #    are leftovers from a failed cascade delete and are wiped; otherwise
    #    their IDs (migrated to the DOI form) also count as already reported.
    existing_ids: set[str] = set()
    if not is_fresh_add and notified_ids:
        existing_ids |= notified_ids

    if not dry_run:
        stale_refs = []
        for ndoc in notifications_ref.where("cited_work_id", "==", work.id).stream():
            if is_fresh_add:
                stale_refs.append(ndoc.reference)
                continue
            data = ndoc.to_dict() or {}
            citing_doi_stored = data.get("citing_work_doi") or ""
            canonical_id = (
                f"{work.id}__{_safe_doc_id(citing_doi_stored)}"
                if citing_doi_stored
                else ndoc.id
            )
            if canonical_id != ndoc.id:
                notifications_ref.document(canonical_id).set(data)
                ndoc.reference.delete()
                logger.info("Migrated notification %s -> %s (uid=%s)", ndoc.id, canonical_id, uid)
            existing_ids.add(canonical_id)

        if stale_refs:
            for ref in stale_refs:
                ref.delete()
            logger.warning(
                "Wiped %d stale notification(s) for freshly added work %s (uid=%s).",
                len(stale_refs), work.id, uid,
            )

    new_count = 0
    skipped_count = 0
    baselined_count = 0
    new_notifications: list[Notification] = []
    pending_writes: list[tuple[Any, dict]] = []

    for item in merged:
        keys: set[str] = item["_keys"]
        # DOI is the stable document ID when there is one; DOIs are case
        # insensitive, so lowercase them to avoid twin documents.
        citing_doi: str = (item.get("doi") or "").lower()
        citing_id: str = citing_doi or item.get("id") or ""
        if not citing_id:
            continue
        doc_id = f"{work.id}__{_safe_doc_id(citing_id)}"

        if keys & known_keys or doc_id in existing_ids:
            known_keys |= keys
            skipped_count += 1
            continue

        if baseline and not _published_since(item, recent_start):
            known_keys |= keys
            baselined_count += 1
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would write notification %s: '%s' cites '%s'",
                doc_id, item["title"], work.title,
            )

        notification = Notification(
            id=doc_id,
            cited_work_id=work.id,
            cited_work_title=work.title,
            citing_work_id=citing_id,
            citing_work_title=_truncate(item["title"], _TITLE_MAX_CHARS),
            citing_work_doi=citing_doi or None,
            citing_work_url=item.get("url"),
            citing_authors=[
                _truncate(a, _AUTHOR_NAME_MAX_CHARS)
                for a in item.get("authors", [])
            ],
            citing_affiliations=item.get("affiliations", []),
            citing_year=item.get("year"),
            citing_publication_date=item.get("publication_date"),
            seen=False,
            emailed=False,
            created_at=now,
        )

        if not dry_run:
            doc_data = notification.model_dump()
            doc_data["created_at"] = now
            pending_writes.append((notifications_ref.document(doc_id), doc_data))

        known_keys |= keys
        existing_ids.add(doc_id)
        new_count += 1
        new_notifications.append(notification)

    if pending_writes:
        _commit_in_batches(db, [("set", ref, data) for ref, data in pending_writes])
        logger.info("Wrote %d notification(s) for uid=%s", len(pending_writes), uid)

    logger.info(
        "Work %s (uid=%s): %d new, %d already reported, %d older recorded at baseline.",
        work.id, uid, new_count, skipped_count, baselined_count,
    )

    # 5. Record what was checked. When every source failed nothing was
    #    checked, so the timestamp stays (a fresh add stays fresh). The
    #    baseline only counts as done when no source failed; otherwise a
    #    source that comes back tomorrow would look like a year of new
    #    citations.
    if not dry_run:
        update: dict[str, Any] = {"last_check_failed_sources": failed}
        if not all_sources_failed:
            update["last_checked_at"] = now
        if existing_ids:
            update["notified_ids"] = sorted(existing_ids)
        if known_keys:
            update["notified_keys"] = sorted(known_keys)
        if baseline and not failed:
            update["citation_window"] = _CITATION_WINDOW_VERSION
        (
            db.collection("users")
            .document(uid)
            .collection("trackedWorks")
            .document(work.id)
            .update(update)
        )

    return new_count, new_notifications


_EMAIL_RETRY_DAYS = 7


def _pending_email_notifications(uid: str, db: Any) -> list[tuple[Any, Notification]]:
    """Notifications from the last week whose alert email has not gone out.

    Only documents written with ``emailed: False`` match; older documents
    have no such field and are never re-sent.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_EMAIL_RETRY_DAYS)
    out: list[tuple[Any, Notification]] = []
    ref = db.collection("users").document(uid).collection("notifications")
    for doc in ref.where("emailed", "==", False).stream():
        data = doc.to_dict() or {}
        created = _firestore_dt(data.get("created_at"))
        if created is not None and created < cutoff:
            continue
        try:
            fields = {k: v for k, v in data.items() if k in Notification.model_fields and k != "id"}
            fields["created_at"] = created
            out.append((doc.reference, Notification(id=doc.id, **fields)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping unreadable notification %s (uid=%s): %s", doc.id, uid, exc)
    out.sort(key=lambda pair: pair[1].created_at or datetime.min.replace(tzinfo=timezone.utc))
    return out


_LOOKBACK_DAYS = 365
_RECENT_DAYS = 30
# Bumped when the meaning of "already reported" changes and every work needs
# one quiet baseline check (2 = identity keys over a one year window,
# 3 = ACL Anthology papers also looked up by DOI in Semantic Scholar, which
# surfaces citations those papers never had before, 4 = OpenCitations and
# Europe PMC added as sources).
_CITATION_WINDOW_VERSION = 4
# Crossref is asked one DOI at a time, so cap how many it fills in per work.
_MAX_CROSSREF_LOOKUPS = 25


async def _hydrate_extra_citations(
    oc_refs: list[dict],
    epmc_normalized: list[dict],
    normalized: list[dict],
    known_keys: set[str],
    work_id: str,
) -> tuple[list[dict], bool]:
    """
    Full records for citing papers that OpenCitations reported by identifier
    only, and OpenAlex records for papers only Europe PMC found (OpenAlex has
    cleaner affiliations).

    Papers another source already returned, or that were reported before,
    are skipped, so this usually costs nothing. Returns the records and
    whether a lookup failed.
    """
    already: set[str] = set(known_keys)
    for item in normalized:
        already |= keys_for_normalized(item)
    seen = set(already)

    def _ref_keys(ref: dict) -> set[str]:
        doi, oa_id = ref.get("doi"), ref.get("openalex_id")
        return ({f"doi:{doi}"} if doi else set()) | ({f"id:{oa_id.lower()}"} if oa_id else set())

    want_ids: list[str] = []
    want_dois: list[str] = []
    new_refs: list[dict] = []
    for ref in oc_refs:
        keys = _ref_keys(ref)
        if keys & seen:
            continue
        seen |= keys
        new_refs.append(ref)
        if ref.get("openalex_id"):
            want_ids.append(ref["openalex_id"])
        else:
            want_dois.append(ref["doi"])
    for item in epmc_normalized:
        if item.get("doi") and not (keys_for_normalized(item) & seen):
            want_dois.append(item["doi"])

    if not want_ids and not want_dois:
        return [], False

    try:
        raws = await openalex_svc.get_works_by_ids(openalex_ids=want_ids, dois=want_dois)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not look up %d extra citing paper(s) for %s: %s",
                       len(want_ids) + len(want_dois), work_id, exc)
        return [], True

    records: list[dict] = []
    found: set[str] = set()
    for raw in raws:
        rec = openalex_svc.normalize_citing_work(raw)
        found |= keys_for_normalized(rec)
        # Known to OpenAlex as front matter or retracted: not worth an alert,
        # and not worth asking Crossref about either.
        if not (raw.get("is_paratext") or raw.get("is_retracted")):
            records.append(rec)
    for item in epmc_normalized:
        found |= keys_for_normalized(item)

    # OpenCitations papers OpenAlex does not have at all: ask Crossref.
    missing = [
        ref["doi"] for ref in new_refs
        if ref.get("doi") and not (_ref_keys(ref) & found)
    ][:_MAX_CROSSREF_LOOKUPS]
    for doi in missing:
        rec = await crossref_svc.get_citing_metadata(doi)
        if rec:
            records.append(rec)

    logger.info("Filled in %d extra citing paper(s) for %s", len(records), work_id)
    return records, False


def _published_since(item: dict, date_str: str) -> bool:
    """Published on or after *date_str*; undated papers fall back to year."""
    pub = item.get("publication_date") or ""
    if pub:
        return pub >= date_str
    return (item.get("year") or 0) >= int(date_str[:4])


# ---------------------------------------------------------------------------
# Full-user-sweep job
# ---------------------------------------------------------------------------


_user_locks: dict[str, threading.Lock] = {}
_user_locks_guard = threading.Lock()


def _user_lock(uid: str) -> threading.Lock:
    with _user_locks_guard:
        return _user_locks.setdefault(uid, threading.Lock())


async def run_job_for_user(
    uid: str,
    user_data: dict,
    db: Any,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
    stats: dict[str, int] | None = None,
    deadline: float | None = None,
    checked_since: datetime | None = None,
) -> tuple[int, int]:
    """
    Run citation checks for all tracked works belonging to a single user.

    Returns (works_processed, new_notifications). When *stats* is given it is
    filled with per-source failure counts for the run's health summary.

    *deadline* (``time.monotonic()``) stops starting new works once passed;
    the user's email then waits for the call that finishes them, and
    ``stats["incomplete"]`` is set to 1. *checked_since* skips works checked
    at or after that time, so the next call carries on from there.

    One check per user at a time: a manual "check now" during the nightly
    sweep would otherwise find the same citations twice and email them twice.
    The second caller skips the user instead of waiting.
    """
    lock = _user_lock(uid)
    if not lock.acquire(blocking=False):
        logger.info("Skipping uid=%s: a citation check for this user is already running.", uid)
        return 0, 0
    try:
        return await _run_job_for_user_locked(
            uid, user_data, db, email_service, dry_run, settings, stats, deadline, checked_since
        )
    finally:
        lock.release()


async def _run_job_for_user_locked(
    uid: str,
    user_data: dict,
    db: Any,
    email_service: ModuleType,
    dry_run: bool,
    settings: Any,
    stats: dict[str, int] | None,
    deadline: float | None = None,
    checked_since: datetime | None = None,
) -> tuple[int, int]:
    if settings is None:
        from citey.config import get_settings
        settings = get_settings()

    logger.info("Processing user uid=%s", uid)

    works_docs = (
        db.collection("users").document(uid).collection("trackedWorks").stream()
    )
    works: list[TrackedWork] = []
    notified_by_work: dict[str, set[str]] = {}
    keys_by_work: dict[str, set[str]] = {}
    baseline_by_work: dict[str, bool] = {}
    works_ref = db.collection("users").document(uid).collection("trackedWorks")
    for wdoc in works_docs:
        wdata = wdoc.to_dict() or {}
        stored_oa_id = wdata.get("openalex_id")
        if stored_oa_id and not is_openalex_work_id(stored_oa_id):
            # Older cross-source imports stored "S2:…"/"pubmed:…" here and
            # seeded openalex_citation_count with that source's number.
            # Clear both; the check below resolves the real ID by DOI.
            logger.info("Clearing non-OpenAlex id %s on work %s (uid=%s)", stored_oa_id, wdoc.id, uid)
            if not dry_run:
                works_ref.document(wdoc.id).update({"openalex_id": None, "openalex_citation_count": None})
        works.append(_doc_to_tracked_work(wdoc.id, wdata))
        notified_by_work[wdoc.id] = set(wdata.get("notified_ids") or [])
        keys_by_work[wdoc.id] = set(wdata.get("notified_keys") or [])
        baseline_by_work[wdoc.id] = wdata.get("citation_window") == _CITATION_WINDOW_VERSION

    user_new_notifications: list[Notification] = []
    works_processed = 0
    source_failures: list[str] = []
    incomplete = False

    to_check = [
        w for w in works
        if not (checked_since and w.last_checked_at and w.last_checked_at >= checked_since)
    ]
    for work in to_check:
        if deadline is not None and time.monotonic() >= deadline:
            incomplete = True
            logger.info(
                "Time budget reached for uid=%s after %d work(s); %d left for the next batch.",
                uid, works_processed, len(to_check) - works_processed,
            )
            break
        works_processed += 1
        try:
            count, notifications = await process_tracked_work(
                uid=uid, work=work, db=db, dry_run=dry_run,
                notified_ids=notified_by_work.get(work.id),
                source_failures=source_failures,
                notified_keys=keys_by_work.get(work.id),
                baseline_done=baseline_by_work.get(work.id, False),
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
            from citey.services.semantic_scholar import get_citation_counts

            from citey.services.semantic_scholar import _clean_doi

            dois = [w.doi for w in works if w.doi]
            if dois:
                s2_counts = await get_citation_counts(dois)
                for work in works:
                    if not work.doi:
                        continue
                    s2_count = s2_counts.get(_clean_doi(work.doi).lower())
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
            oa_ids = [w.openalex_id for w in works if is_openalex_work_id(w.openalex_id)]
            if oa_ids:
                oa_counts = await openalex_svc.get_citation_counts(oa_ids)
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

    oa_failed = source_failures.count("openalex")
    s2_failed = source_failures.count("semantic_scholar")
    oc_failed = source_failures.count("opencitations")
    epmc_failed = source_failures.count("europe_pmc")
    logger.info(
        "Check health uid=%s: %d work(s), failures: OpenAlex %d, Semantic Scholar %d, "
        "OpenCitations %d, Europe PMC %d",
        uid, works_processed, oa_failed, s2_failed, oc_failed, epmc_failed,
    )
    if stats is not None:
        stats["openalex_failures"] = stats.get("openalex_failures", 0) + oa_failed
        stats["semantic_scholar_failures"] = stats.get("semantic_scholar_failures", 0) + s2_failed
        stats["opencitations_failures"] = stats.get("opencitations_failures", 0) + oc_failed
        stats["europe_pmc_failures"] = stats.get("europe_pmc_failures", 0) + epmc_failed
        stats["incomplete"] = 1 if incomplete else 0
    if incomplete:
        # The email goes out with the batch that finishes this user, so the
        # digest is one message, not one per batch.
        return works_processed, len(user_new_notifications)

    # Send an immediate email when new citations are found.
    to_email: str | None = resolve_recipient(user_data)
    notify_enabled: bool = user_data.get("notify_enabled", True)

    email_verified = True
    try:
        user_record = firebase_auth.get_user(uid)
        email_verified = user_record.email_verified
    except Exception as exc:
        logger.warning("Could not check email_verified for uid=%s: %s", uid, exc)

    # What to email: every notification not yet emailed from the last week,
    # which includes this run's and any whose earlier send failed (during the
    # October domain outage those were marked sent and lost). They are marked
    # emailed only after Resend accepts the message.
    to_send: list[tuple[Any, Notification]] = (
        [] if dry_run else _pending_email_notifications(uid, db)
    )
    if dry_run:
        to_send = [(None, n) for n in user_new_notifications]

    if to_send and to_email and not email_verified:
        logger.info("Skipping citation email: uid=%s email not verified.", uid)

    if to_send and to_email and notify_enabled and email_verified:
        notifications = [n for _, n in to_send]
        if dry_run:
            logger.info("[DRY RUN] Would email %s with %d new citation(s).", to_email, len(notifications))
        else:
            try:
                citation_groups = _group_notifications(notifications)
                recipient_name: str = user_data.get("display_name") or to_email
                await email_service.send_digest_email(
                    to_email=to_email,
                    recipient_name=recipient_name,
                    citation_groups=citation_groups,
                    total_citations=len(notifications),
                    digest_date=datetime.now(tz=timezone.utc),
                    settings=settings,
                    uid=uid,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to send citation email to %s (uid=%s); %d citation(s) stay pending: %s",
                    to_email, uid, len(notifications), exc, exc_info=True,
                )
            else:
                _commit_in_batches(db, [("update", ref, {"emailed": True}) for ref, _ in to_send])
                logger.info(
                    "Citation email sent to %s (uid=%s): %d citation(s) across %d paper(s).",
                    to_email, uid, len(notifications), len(citation_groups),
                )

    return works_processed, len(user_new_notifications)


def users_after(db: Any, cursor: str | None) -> list[Any]:
    """Every user document ordered by uid, keeping only those after *cursor*.

    The all-users jobs run in batches so each request fits a host's time
    limit (Vercel Hobby stops a request after 300 s). A batch returns the
    last uid it finished as its cursor and the next batch starts after it.

    The whole list is read first: a Firestore stream left open while each
    user is processed (minutes) times out with "Deadline Exceeded".
    """
    docs = sorted(db.collection("users").stream(), key=lambda d: d.id)
    if cursor is None:
        return docs
    return [d for d in docs if d.id > cursor]


def out_of_time(started: float, time_budget_seconds: float | None) -> bool:
    """True once a batch has used its budget. No budget means no limit."""
    return (
        time_budget_seconds is not None
        and time.monotonic() - started >= time_budget_seconds
    )


async def run_job_for_all_users(
    db: Any,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
    cursor: str | None = None,
    time_budget_seconds: float | None = None,
    checked_since: datetime | None = None,
) -> dict[str, Any]:
    """
    Run citation checks for every user in Firestore, in uid order.

    *cursor* resumes after that uid. With *time_budget_seconds*, no new user
    is started once the budget is used, and the user already running stops
    before their next paper. That user is then the next batch's first, and
    *checked_since* (the run's start) lets it skip papers already checked.

    Returns a summary dict:
        {users_processed, works_processed, new_notifications, next_cursor, ...}
    next_cursor is the uid to resume after, or None when every user is done.
    """
    if settings is None:
        from citey.config import get_settings
        settings = get_settings()

    users_processed = 0
    users_failed = 0
    works_processed = 0
    total_new_notifications = 0
    stats: dict[str, int] = {
        "openalex_failures": 0,
        "semantic_scholar_failures": 0,
        "opencitations_failures": 0,
        "europe_pmc_failures": 0,
    }

    started = time.monotonic()
    next_cursor: str | None = None
    last_done: str | None = cursor

    auth_uids = _get_auth_uids()
    deadline = started + time_budget_seconds if time_budget_seconds is not None else None
    if checked_since is not None and checked_since.tzinfo is None:
        checked_since = checked_since.replace(tzinfo=timezone.utc)
    for user_doc in users_after(db, cursor):
        if out_of_time(started, time_budget_seconds):
            next_cursor = last_done
            break
        uid: str = user_doc.id
        previous_done, last_done = last_done, uid
        if uid not in auth_uids:
            logger.warning("Skipping orphaned Firestore user uid=%s in citation job", uid)
            continue
        user_data: dict = user_doc.to_dict() or {}
        users_processed += 1

        user_stats: dict[str, int] = {}
        try:
            wp, nn = await run_job_for_user(
                uid=uid,
                user_data=user_data,
                db=db,
                email_service=email_service,
                dry_run=dry_run,
                settings=settings,
                stats=user_stats,
                deadline=deadline,
                checked_since=checked_since,
            )
        except Exception as exc:  # noqa: BLE001
            # One user's failure (a Firestore timeout, a bad document) must
            # not cost everyone else their check.
            users_failed += 1
            logger.error("Citation check failed for uid=%s: %s", uid, exc, exc_info=True)
            continue
        works_processed += wp
        total_new_notifications += nn
        incomplete = user_stats.pop("incomplete", 0)
        for key, value in user_stats.items():
            stats[key] = stats.get(key, 0) + value
        if incomplete:
            # Resume this same user next batch. Without checked_since the
            # next batch would start their papers over and never finish.
            if checked_since is None:
                logger.warning("uid=%s ran out of time with no checked_since; it may not finish.", uid)
            next_cursor = previous_done or ""
            break

    summary = {
        "users_processed": users_processed,
        "users_failed": users_failed,
        "works_processed": works_processed,
        "new_notifications": total_new_notifications,
        **stats,
        "next_cursor": next_cursor,
    }
    logger.info("Job batch complete: %s", summary)
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

    A notification is stale once Citey found it more than
    ``_NOTIFICATION_TTL_DAYS`` days ago. The citing paper's publication date
    does not matter: a late indexed citation stays visible for its 30 days.
    Returns the number of notifications deleted (or that would be deleted in
    dry-run mode).
    """
    cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=_NOTIFICATION_TTL_DAYS)

    notifs_ref = db.collection("users").document(uid).collection("notifications")

    to_delete: dict[str, Any] = {}
    for doc in notifs_ref.where("created_at", "<", cutoff_dt).stream():
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

    auth_uids = _get_auth_uids()
    # Read the whole list first: a Firestore stream left open while each
    # user is processed (minutes) times out with "Deadline Exceeded".
    for user_doc in list(db.collection("users").stream()):
        uid: str = user_doc.id
        if uid not in auth_uids:
            logger.warning("Skipping orphaned Firestore user uid=%s in notification cleanup", uid)
            continue
        users_processed += 1
        count = await prune_user_notifications(uid, db, dry_run)
        total_deleted += count

    summary = {"users_processed": users_processed, "notifications_deleted": total_deleted}
    logger.info("Notification cleanup complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

_BATCH_LIMIT = 500  # Firestore's max writes per batch


def _commit_in_batches(db: Any, ops: list[tuple[str, Any, Any]]) -> None:
    """Apply ("set"|"update"|"delete", ref, data) ops in chunks of 500."""
    for i in range(0, len(ops), _BATCH_LIMIT):
        batch = db.batch()
        for op, ref, data in ops[i : i + _BATCH_LIMIT]:
            if op == "set":
                batch.set(ref, data)
            elif op == "update":
                batch.update(ref, data)
            else:
                batch.delete(ref)
        batch.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_auth_uids() -> set[str]:
    """Return the set of all Firebase Auth user UIDs (paginated, single sweep)."""
    uids: set[str] = set()
    page = firebase_auth.list_users()
    while page:
        for user in page.users:
            uids.add(user.uid)
        page = page.get_next_page()
    return uids


async def cleanup_orphan_users(db: Any, dry_run: bool = False) -> dict:
    """
    Delete Firestore user documents (and their subcollections) that have no
    corresponding Firebase Auth account.
    """
    auth_uids = _get_auth_uids()
    orphans_found = 0
    orphans_deleted = 0

    # Read the whole list first: a Firestore stream left open while each
    # user is processed (minutes) times out with "Deadline Exceeded".
    for user_doc in list(db.collection("users").stream()):
        uid: str = user_doc.id
        if uid in auth_uids:
            continue
        orphans_found += 1
        logger.warning("Orphaned Firestore user found: uid=%s", uid)
        if not dry_run:
            for subcoll in ("trackedWorks", "notifications"):
                for doc in db.collection("users").document(uid).collection(subcoll).stream():
                    doc.reference.delete()
            user_doc.reference.delete()
            orphans_deleted += 1
            logger.info("Deleted orphaned Firestore user: uid=%s", uid)

    return {
        "orphans_found": orphans_found,
        "orphans_deleted": orphans_deleted,
        "message": (
            f"Found {orphans_found} orphaned user(s) — dry run, nothing deleted."
            if dry_run
            else f"Deleted {orphans_deleted} orphaned user(s)."
        ),
    }


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

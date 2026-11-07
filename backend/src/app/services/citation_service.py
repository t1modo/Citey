"""
Citation-checking orchestration service.

This module is responsible for:
1. Iterating a user's tracked works.
2. Querying OpenAlex, Semantic Scholar, OpenCitations and Europe PMC for
   new citing papers since the last check.
3. Recording each new citation once per paper, and an alert for every user
   tracking it (Postgres, through the stores).
4. Emailing each user a digest of their alerts not yet emailed.

A paper is one shared row, so co-authors share its check: whoever's run
reaches it first checks it, and everyone tracking it gets the alert.
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
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.concurrency import run_blocking
from app.models import Work
from app.schemas import Notification, is_openalex_work_id
from app.services import alert_service, convert
from app.services.citing_identity import is_junk, keys_for_normalized, merge_records
from app.services import crossref as crossref_svc
from app.services import europe_pmc as europe_pmc_svc
from app.services import openalex as openalex_svc
from app.services import opencitations as opencitations_svc
from app.services import semantic_scholar as s2_svc

from app.services.email_service import resolve_recipient
from app.store import AlertStore, CitationStore, UserStore, WorkStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-work processing
# ---------------------------------------------------------------------------


async def process_tracked_work(
    session: AsyncSession,
    work: Work,
    dry_run: bool = False,
    source_failures: list[str] | None = None,
    uid: str = "",
) -> tuple[int, list[Notification]]:
    """
    Check *work* for new citations and record them.

    "New" means not reported before: none of the citing paper's identity
    keys is already recorded for this paper (or was reported while the data
    lived in Firestore). Each new citation is recorded once, and every user
    tracking the paper gets an alert. *uid* only labels the logs.

    Returns (new_citation_count, the new citations as Notifications).
    """
    # 1. Resolve the OpenAlex work ID — only DOI/OpenAlex ID are used; no
    #    pre-supplied metadata is sent to the API.
    works = WorkStore(session)
    openalex_id: str | None = work.openalex_id
    if not openalex_id and work.doi:
        logger.info(
            "No cached OpenAlex ID for work %s — resolving from doi=%s (uid=%s)",
            work.key, work.doi, uid,
        )
        raw = await openalex_svc.get_work_by_doi(work.doi)
        if raw:
            openalex_id = raw.get("id")
            # Let the caller's count refresh use the resolved ID this run.
            work.openalex_id = openalex_id
            logger.info("Resolved OpenAlex ID: %s for work %s", openalex_id, work.key)
            if not dry_run and openalex_id:
                await works.update_fields(work.id, openalex_id=openalex_id)
        else:
            logger.warning(
                "OpenAlex returned no result for doi=%s (work %s, uid=%s)",
                work.doi, work.key, uid,
            )

    if not openalex_id and not work.doi:
        logger.warning(
            "No OpenAlex ID or DOI for work %s (uid=%s) — skipping.", work.key, uid
        )
        return 0, []

    if not openalex_id:
        logger.info(
            "OpenAlex ID unavailable for work %s (uid=%s) — will rely on Semantic Scholar.",
            work.key, uid,
        )

    logger.info(
        "Fetching citations for work %s (openalex_id=%s, doi=%s, uid=%s)",
        work.key, openalex_id, work.doi, uid,
    )

    # 2. Fetch from every source in parallel.
    #    Indexes can take weeks to list a new paper, so "new" means "not
    #    reported before" (any identity key in notified_keys), not "published
    #    in the last 30 days". Citing papers from the past year are considered.
    now = datetime.now(tz=timezone.utc)
    window_start = (now - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    recent_start = (now - timedelta(days=_RECENT_DAYS)).strftime("%Y-%m-%d")
    citation_store = CitationStore(session)
    known_keys: set[str] = await citation_store.known_keys(work.id)
    # The first complete check of a paper (or of one tracked before the
    # wider window existed) records older citations silently instead of
    # emailing a year of them at once.
    baseline = work.citation_window != _CITATION_WINDOW_VERSION

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
        logger.warning("OpenAlex citation fetch failed for work %s: %s", work.key, oa_results)
        failed.append("openalex")
        oa_results = []
    if isinstance(s2_results, BaseException):
        logger.warning("S2 citation fetch failed for work %s: %s", work.key, s2_results)
        failed.append("semantic_scholar")
        s2_results = []
    if isinstance(oc_refs, BaseException):
        logger.warning("OpenCitations fetch failed for work %s: %s", work.key, oc_refs)
        failed.append("opencitations")
        oc_refs = []
    if isinstance(epmc_results, BaseException):
        logger.warning("Europe PMC fetch failed for work %s: %s", work.key, epmc_results)
        failed.append("europe_pmc")
        epmc_results = []

    logger.info(
        "OpenAlex: %d | S2: %d | OpenCitations: %d | Europe PMC: %d citing record(s) for %s (uid=%s)",
        len(oa_results), len(s2_results), len(oc_refs), len(epmc_results), work.key, uid,
    )

    # 3. Normalise, drop notices (errata, retractions), and merge every record
    #    of the same paper across sources and versions. OpenAlex comes first,
    #    so its richer metadata wins; the others fill gaps.
    normalized = [openalex_svc.normalize_citing_work(r) for r in oa_results]
    normalized += [s2_svc.normalize_citing_work(r) for r in s2_results]
    epmc_normalized = [europe_pmc_svc.normalize_citing_work(r) for r in epmc_results]
    hydrated, hydrate_failed = await _hydrate_extra_citations(
        oc_refs, epmc_normalized, normalized, known_keys, work.key
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
        work.key, uid, len(merged), len(normalized), junk_count, baseline,
    )

    alert_store = AlertStore(session)
    new_count = 0
    skipped_count = 0
    baselined_count = 0
    new_notifications: list[Notification] = []

    for item in merged:
        keys: set[str] = item["_keys"]
        # DOI is the stable identity when there is one; DOIs are case
        # insensitive, so lowercase them to avoid twins.
        citing_doi: str = (item.get("doi") or "").lower()
        citing_id: str = citing_doi or item.get("id") or ""
        if not citing_id:
            continue

        if keys & known_keys:
            known_keys |= keys
            skipped_count += 1
            continue

        fields = {
            "doi": citing_doi or None,
            "url": item.get("url"),
            "title": _truncate(item["title"], _TITLE_MAX_CHARS),
            "authors": [_truncate(a, _AUTHOR_NAME_MAX_CHARS) for a in item.get("authors", [])],
            "affiliations": item.get("affiliations", []),
            "year": item.get("year"),
            "publication_date": item.get("publication_date"),
        }
        announce = not (baseline and not _published_since(item, recent_start))
        known_keys |= keys
        if not announce:
            # Recorded, so it counts as known, but nobody is alerted.
            baselined_count += 1
            if not dry_run:
                await citation_store.record(work.id, citing_id, keys, fields, found_at=now)
            continue

        if dry_run:
            logger.info("[DRY RUN] Would record citation: '%s' cites '%s'", item["title"], work.title)
        else:
            citation_id, created = await citation_store.record(work.id, citing_id, keys, fields, found_at=now)
            if created:
                await alert_store.add_for_trackers(citation_id, created_at=now)
        new_count += 1
        new_notifications.append(
            Notification(
                id=citing_id,
                cited_work_id=work.key,
                cited_work_title=work.title,
                citing_work_id=citing_id,
                citing_work_title=fields["title"],
                citing_work_doi=fields["doi"],
                citing_work_url=fields["url"],
                citing_authors=fields["authors"],
                citing_affiliations=fields["affiliations"],
                citing_year=fields["year"],
                citing_publication_date=fields["publication_date"],
                created_at=now,
            )
        )

    logger.info(
        "Work %s (uid=%s): %d new, %d already reported, %d older recorded at baseline.",
        work.key, uid, new_count, skipped_count, baselined_count,
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
            work.last_checked_at = now
        if baseline and not failed:
            update["citation_window"] = _CITATION_WINDOW_VERSION
        await works.update_fields(work.id, **update)

    return new_count, new_notifications


_EMAIL_RETRY_DAYS = 7


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
    session: AsyncSession,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
    stats: dict[str, int] | None = None,
    deadline: float | None = None,
    checked_since: datetime | None = None,
) -> tuple[int, int]:
    """
    Run citation checks for every paper *uid* tracks, then email their digest.

    Returns (works_processed, new_citations). When *stats* is given it is
    filled with per-source failure counts for the run's health summary.

    *deadline* (``time.monotonic()``) stops starting new works once passed;
    the user's email then waits for the call that finishes them, and
    ``stats["incomplete"]`` is set to 1. *checked_since* skips papers checked
    at or after that time, so the next call carries on from there; it also
    skips a paper a co-author's run already checked.

    One check per user at a time: a manual "check now" during the nightly
    sweep would otherwise run twice. The second caller skips the user.
    """
    lock = _user_lock(uid)
    if not lock.acquire(blocking=False):
        logger.info("Skipping uid=%s: a citation check for this user is already running.", uid)
        return 0, 0
    try:
        return await _run_job_for_user_locked(
            uid, session, email_service, dry_run, settings, stats, deadline, checked_since
        )
    finally:
        lock.release()


async def _run_job_for_user_locked(
    uid: str,
    session: AsyncSession,
    email_service: ModuleType,
    dry_run: bool,
    settings: Any,
    stats: dict[str, int] | None,
    deadline: float | None = None,
    checked_since: datetime | None = None,
) -> tuple[int, int]:
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    logger.info("Processing user uid=%s", uid)
    user = await UserStore(session).get(uid)
    if user is None:
        logger.info("Skipping uid=%s: no profile.", uid)
        return 0, 0
    user_data = convert.user_data(user)

    work_store = WorkStore(session)
    works: list[Work] = [work for work, _ in await work_store.tracked(uid)]
    for work in works:
        if work.openalex_id and not is_openalex_work_id(work.openalex_id):
            # Older cross-source imports stored "S2:…"/"pubmed:…" here and
            # seeded openalex_citation_count with that source's number.
            # Clear both; the check below resolves the real ID by DOI.
            logger.info("Clearing non-OpenAlex id %s on work %s (uid=%s)", work.openalex_id, work.key, uid)
            work.openalex_id = None
            if not dry_run:
                await work_store.update_fields(work.id, openalex_id=None, openalex_citation_count=None)

    new_citations = 0
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
            count, _ = await process_tracked_work(
                session, work, dry_run=dry_run, source_failures=source_failures, uid=uid
            )
            new_citations += count
            if not dry_run:
                # Each paper's result is kept even if a later one fails.
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            logger.error("Error processing work %s for uid=%s: %s", work.key, uid, exc, exc_info=True)

    # Lifetime citation counts from Semantic Scholar and OpenAlex, in one
    # batch each.
    if not dry_run:
        try:
            from app.services.semantic_scholar import _clean_doi, get_citation_counts

            dois = [w.doi for w in works if w.doi]
            if dois:
                s2_counts = await get_citation_counts(dois)
                for work in works:
                    s2_count = s2_counts.get(_clean_doi(work.doi).lower()) if work.doi else None
                    if s2_count is not None:
                        await work_store.update_fields(work.id, s2_citation_count=s2_count)
                logger.info("Updated S2 citation counts for uid=%s (%d works matched)", uid, len(s2_counts))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch S2 citation counts for uid=%s: %s", uid, exc)
        try:
            oa_ids = [w.openalex_id for w in works if is_openalex_work_id(w.openalex_id)]
            if oa_ids:
                oa_counts = await openalex_svc.get_citation_counts(oa_ids)
                for work in works:
                    if not work.openalex_id:
                        continue
                    short_id = work.openalex_id.removeprefix("https://openalex.org/")
                    oa_count = oa_counts.get(short_id)
                    if oa_count is not None:
                        await work_store.update_fields(work.id, openalex_citation_count=oa_count)
                logger.info("Updated OpenAlex citation counts for uid=%s (%d works matched)", uid, len(oa_counts))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch OpenAlex citation counts for uid=%s: %s", uid, exc)
        await session.commit()

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
        return works_processed, new_citations

    await _email_digest(session, uid, user_data, email_service, settings, dry_run)
    return works_processed, new_citations


async def _email_digest(
    session: AsyncSession,
    uid: str,
    user_data: dict,
    email_service: ModuleType,
    settings: Any,
    dry_run: bool,
) -> None:
    """
    Email every alert from the last week not yet emailed: this run's, any a
    co-author's run created, and any whose earlier send failed. They are
    marked emailed only after Resend accepts the message.
    """
    to_email: str | None = resolve_recipient(user_data)
    if not to_email or not user_data.get("notify_enabled", True):
        return
    since = datetime.now(tz=timezone.utc) - timedelta(days=_EMAIL_RETRY_DAYS)
    to_send = await alert_service.pending_email(session, uid, since)
    if not to_send:
        return

    email_verified = True
    try:
        user_record = await run_blocking(firebase_auth.get_user, uid)
        email_verified = user_record.email_verified
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not check email_verified for uid=%s: %s", uid, exc)
    if not email_verified:
        logger.info("Skipping citation email: uid=%s email not verified.", uid)
        return

    if dry_run:
        logger.info("[DRY RUN] Would email %s with %d citation(s).", to_email, len(to_send))
        return
    citation_groups = _group_notifications(to_send)
    try:
        await email_service.send_digest_email(
            to_email=to_email,
            recipient_name=user_data.get("display_name") or to_email,
            citation_groups=citation_groups,
            total_citations=len(to_send),
            digest_date=datetime.now(tz=timezone.utc),
            settings=settings,
            uid=uid,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to send citation email to %s (uid=%s); %d citation(s) stay pending: %s",
            to_email, uid, len(to_send), exc, exc_info=True,
        )
        return
    await AlertStore(session).mark_emailed([int(n.id) for n in to_send])
    await session.commit()
    logger.info(
        "Citation email sent to %s (uid=%s): %d citation(s) across %d paper(s).",
        to_email, uid, len(to_send), len(citation_groups),
    )


def out_of_time(started: float, time_budget_seconds: float | None) -> bool:
    """True once a batch has used its budget. No budget means no limit."""
    return (
        time_budget_seconds is not None
        and time.monotonic() - started >= time_budget_seconds
    )


async def run_job_for_all_users(
    session: AsyncSession,
    email_service: ModuleType,
    dry_run: bool = False,
    settings: Any = None,
    cursor: str | None = None,
    time_budget_seconds: float | None = None,
    checked_since: datetime | None = None,
) -> dict[str, Any]:
    """
    Run citation checks for every user, in uid order.

    *cursor* resumes after that uid. With *time_budget_seconds*, no new user
    is started once the budget is used, and the user already running stops
    before their next paper. That user is then the next batch's first, and
    *checked_since* (the run's start) lets it skip papers already checked.

    Returns a summary dict:
        {users_processed, works_processed, new_notifications, next_cursor, ...}
    next_cursor is the uid to resume after, or None when every user is done.
    """
    if settings is None:
        from app.config import get_settings
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

    auth_uids = await _get_auth_uids()
    deadline = started + time_budget_seconds if time_budget_seconds is not None else None
    if checked_since is not None and checked_since.tzinfo is None:
        checked_since = checked_since.replace(tzinfo=timezone.utc)
    for uid in await UserStore(session).ids_after(cursor):
        if out_of_time(started, time_budget_seconds):
            next_cursor = last_done
            break
        previous_done, last_done = last_done, uid
        if uid not in auth_uids:
            logger.warning("Skipping user uid=%s with no sign-in account in citation job", uid)
            continue
        users_processed += 1

        user_stats: dict[str, int] = {}
        try:
            wp, nn = await run_job_for_user(
                uid=uid,
                session=session,
                email_service=email_service,
                dry_run=dry_run,
                settings=settings,
                stats=user_stats,
                deadline=deadline,
                checked_since=checked_since,
            )
        except Exception as exc:  # noqa: BLE001
            # One user's failure must not cost everyone else their check.
            await session.rollback()
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


async def prune_user_notifications(uid: str, session: AsyncSession, dry_run: bool = False) -> int:
    """
    Delete one user's alerts found more than ``_NOTIFICATION_TTL_DAYS`` days
    ago (by when Citey found them, not when the citing paper came out).
    Returns how many were (or, in a dry run, would be) deleted.
    """
    before = datetime.now(tz=timezone.utc) - timedelta(days=_NOTIFICATION_TTL_DAYS)
    count = await AlertStore(session).prune(before, uid=uid, dry_run=dry_run)
    if count:
        action = "[DRY RUN] would delete" if dry_run else "deleted"
        logger.info("Prune uid=%s: %s %d notification(s) older than %d days.",
                    uid, action, count, _NOTIFICATION_TTL_DAYS)
    if not dry_run:
        await session.commit()
    return count


async def cleanup_old_notifications(session: AsyncSession, dry_run: bool = False) -> dict:
    """
    Delete every user's alerts older than ``_NOTIFICATION_TTL_DAYS`` days.
    The citations themselves stay: they are the papers' record.

    Returns a summary dict: {users_processed, notifications_deleted}.
    """
    before = datetime.now(tz=timezone.utc) - timedelta(days=_NOTIFICATION_TTL_DAYS)
    deleted = await AlertStore(session).prune(before, dry_run=dry_run)
    if not dry_run:
        await session.commit()
    summary = {
        "users_processed": len(await UserStore(session).ids_after()),
        "notifications_deleted": deleted,
    }
    logger.info("Notification cleanup complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Accounts without a sign-in record
# ---------------------------------------------------------------------------


def _list_auth_uids() -> set[str]:
    """Every Firebase Auth user UID (paginated). Blocking."""
    uids: set[str] = set()
    page = firebase_auth.list_users()
    while page:
        for user in page.users:
            uids.add(user.uid)
        page = page.get_next_page()
    return uids


async def _get_auth_uids() -> set[str]:
    """Every Firebase Auth user UID, fetched off the event loop."""
    return await run_blocking(_list_auth_uids)


async def cleanup_orphan_users(session: AsyncSession, dry_run: bool = False) -> dict:
    """
    Delete accounts with no Firebase Auth record: their profile, tracking and
    alerts (papers and citations stay for anyone else tracking them).
    """
    auth_uids = await _get_auth_uids()
    store = UserStore(session)
    orphans = [uid for uid in await store.ids_after() if uid not in auth_uids]
    for uid in orphans:
        logger.warning("User with no sign-in account found: uid=%s", uid)
        if not dry_run:
            await store.delete_by_id(uid)
            logger.info("Deleted user with no sign-in account: uid=%s", uid)
    if not dry_run:
        await session.commit()
    deleted = 0 if dry_run else len(orphans)
    return {
        "orphans_found": len(orphans),
        "orphans_deleted": deleted,
        "message": (
            f"Found {len(orphans)} orphaned user(s) — dry run, nothing deleted."
            if dry_run
            else f"Deleted {deleted} orphaned user(s)."
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

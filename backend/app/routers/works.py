import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import enforce_cooldown, get_current_user
from app.firebase_client import get_db
from app.models import AddWorkRequest, ImportByAuthorRequest, TrackedWork
from app.services.crossref import resolve_doi
from app.services.normalize import dedupe_works_by_title, doi_to_work_id, normalize_doi
from app.services.openalex import extract_topics, extract_venue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/works", tags=["works"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiters for search endpoints
# ---------------------------------------------------------------------------

_SEARCH_RATE_LIMIT = 5       # requests
_SEARCH_RATE_WINDOW = 60     # per N seconds
_PAPER_AUTHORS_RATE_LIMIT = 10
_IMPORT_COOLDOWN = 300       # seconds between bulk imports per user

_author_search_timestamps: dict[str, list[float]] = defaultdict(list)
_paper_authors_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(
    store: dict[str, list[float]],
    uid: str,
    limit: int,
    window: int = _SEARCH_RATE_WINDOW,
) -> None:
    """Raise HTTP 429 if uid has exceeded limit requests within the window."""
    now = time.monotonic()
    store[uid] = [t for t in store[uid] if now - t < window]
    if len(store[uid]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before searching again.",
        )
    store[uid].append(now)


def _name_tokens(name: str) -> list[str]:
    """Lowercase, replace separators with spaces, return non-empty tokens."""
    return [t for t in re.sub(r"[^a-z\s]", "", name.lower().replace(".", " ").replace("-", " ")).split() if t]


def _given_names_match(short_given: list[str], long_given: list[str]) -> bool:
    """Match given-name token lists, allowing initial abbreviations and middle-name omission."""
    if not short_given:
        return True  # Only family name — accept.
    si = 0
    for token in long_given:
        if si >= len(short_given):
            break
        s = short_given[si]
        if s == token or (len(s) == 1 and token.startswith(s)) or (len(token) == 1 and s.startswith(token)):
            si += 1
    return si == len(short_given)


def _names_match(a: str, b: str) -> bool:
    """
    Fuzzy name match that tolerates:
      - Case differences
      - Middle name omission: "Timothy Do" matches "Timothy Khang Do"
      - First initials: "T. Do" matches "Timothy Do"
      - Compound surnames: "Yann LeCun" matches "Yann Le Cun"
      - Reversed order is NOT allowed — last name must match last name.
    """
    a_tok = _name_tokens(a)
    b_tok = _name_tokens(b)
    if not a_tok or not b_tok:
        return False
    if a_tok == b_tok:
        return True
    # Standard case: last token is the family name and must match exactly.
    if a_tok[-1] == b_tok[-1]:
        short_given = a_tok[:-1] if len(a_tok) <= len(b_tok) else b_tok[:-1]
        long_given = a_tok[:-1] if len(a_tok) > len(b_tok) else b_tok[:-1]
        return _given_names_match(short_given, long_given)
    # Compound-surname fallback: last 2 tokens of one name concatenate to match
    # the last token of the other (e.g. "Le"+"Cun" == "lecun").
    if len(a_tok) >= 2 and "".join(a_tok[-2:]) == b_tok[-1]:
        a_given, b_given = a_tok[:-2], b_tok[:-1]
        short_given = a_given if len(a_given) <= len(b_given) else b_given
        long_given = a_given if len(a_given) > len(b_given) else b_given
        return _given_names_match(short_given, long_given)
    if len(b_tok) >= 2 and "".join(b_tok[-2:]) == a_tok[-1]:
        b_given, a_given = b_tok[:-2], a_tok[:-1]
        short_given = a_given if len(a_given) <= len(b_given) else b_given
        long_given = a_given if len(a_given) > len(b_given) else b_given
        return _given_names_match(short_given, long_given)
    return False


def _author_in_paper(paper_authors: list[str], names_to_check: list[str]) -> bool:
    """Return True if any name in names_to_check fuzzy-matches any paper author."""
    for check in names_to_check:
        for author in paper_authors:
            if _names_match(check, author):
                return True
    return False


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


@router.post("", response_model=TrackedWork, status_code=status.HTTP_201_CREATED)
async def add_work(
    body: AddWorkRequest,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> TrackedWork:
    """
    Resolve a DOI via Crossref, then store it in the user's trackedWorks subcollection.
    Uses the DOI (with slashes replaced) as the document ID to prevent duplicates.
    """
    work_info = await resolve_doi(body.doi)

    # --- Author presence check ---
    # When the account is linked to an author, verify the paper's author list
    # includes that author (or one of their known aliases) before adding.
    # The user can pass force=True to bypass this check.
    if not body.force:
        user_snap = db.collection("users").document(uid).get()
        user_data = user_snap.to_dict() or {} if user_snap.exists else {}
        # Both fields must be present — if either was cleared by an unlink the
        # check is inactive.  This prevents a stale linked_author_name from
        # blocking additions after the author profile has been reset.
        linked_id: str | None = user_data.get("linked_author_id")
        linked_name: str | None = user_data.get("linked_author_name")
        if linked_id and linked_name:
            aliases: list[str] = user_data.get("name_aliases") or []
            names_to_check = [linked_name] + aliases
            paper_authors: list[str] = work_info.get("authors", [])
            if not _author_in_paper(paper_authors, names_to_check):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "author_not_found",
                        "linked_author": linked_name,
                        "paper_title": work_info.get("title", ""),
                        "paper_authors": paper_authors,
                    },
                )

    # If Crossref didn't return an OpenAlex ID (the normal case), resolve it
    # eagerly now so that the first citation check can proceed immediately
    # without a separate lookup step.  Also extract topics/venue/type here.
    if not work_info.get("openalex_id"):
        from app.services.openalex import get_work_by_doi as _oa_lookup
        oa_raw = await _oa_lookup(work_info["doi"])
        if oa_raw:
            work_info["openalex_id"] = oa_raw.get("id")
            work_info["openalex_citation_count"] = oa_raw.get("cited_by_count")
            work_info["topics"] = extract_topics(oa_raw)
            work_info["venue"] = extract_venue(oa_raw)
            work_info["work_type"] = oa_raw.get("type")
            # OpenAlex author names come from entity resolution and are more
            # reliable than raw publisher-submitted names from Crossref.
            oa_authors = [
                s for s in (
                    (a.get("author") or {}).get("display_name", "").strip()
                    for a in (oa_raw.get("authorships") or [])
                )
                if s
            ]
            if oa_authors:
                work_info["authors"] = oa_authors
            logger.info("Resolved OpenAlex ID for %s: %s", work_info["doi"], work_info["openalex_id"])

    # For arXiv papers, override author names with the arXiv API which stores
    # names exactly as submitted — more reliable than OpenAlex abbreviations.
    from app.services.arxiv_api import get_authors as _arxiv_authors
    arxiv_names = await _arxiv_authors(work_info["doi"])
    if arxiv_names:
        work_info["authors"] = arxiv_names

    # Normalise DOI to lowercase for consistent Firestore document IDs.
    # DOIs are case-insensitive; mixing cases creates phantom duplicates.
    work_info["doi"] = normalize_doi(work_info["doi"])
    work_id = doi_to_work_id(work_info["doi"])

    ref = db.collection("users").document(uid).collection("trackedWorks").document(work_id)
    snapshot = ref.get()
    if snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This work is already being tracked.",
        )

    now = datetime.now(tz=timezone.utc)
    doc_data: dict = {
        "doi": work_info["doi"],
        "openalex_id": work_info.get("openalex_id"),
        "title": work_info["title"],
        "authors": work_info.get("authors", []),
        "year": work_info.get("year"),
        "venue": work_info.get("venue"),
        "work_type": work_info.get("work_type"),
        "topics": work_info.get("topics", []),
        "added_at": now,
        "last_checked_at": None,
        "openalex_citation_count": work_info.get("openalex_citation_count"),
    }
    ref.set(doc_data)
    # Adding a paper by hand undoes an earlier dismissal.
    from firebase_admin import firestore
    db.collection("users").document(uid).set(
        {"dismissed_work_ids": firestore.ArrayRemove([work_id])}, merge=True
    )
    logger.info("Added tracked work %s for uid=%s", work_id, uid)

    return _doc_to_tracked_work(work_id, doc_data)


def _format_author_candidate(r: dict) -> dict:
    """Extract the fields we expose to the frontend from a raw OpenAlex author dict."""
    # Affiliations: deduplicate institutions, keep most-recent years
    seen: set[str] = set()
    affiliations: list[dict] = []
    for a in r.get("affiliations", []):
        name = a.get("institution", {}).get("display_name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        years: list[int] = sorted(a.get("years", []))
        affiliations.append(
            {
                "name": name,
                "year_range": f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0]) if years else None,
            }
        )
        if len(affiliations) == 3:
            break

    # Topics: top 3 by score
    topics = [
        t.get("display_name", "")
        for t in r.get("topics", [])[:3]
        if t.get("display_name")
    ]

    return {
        "id": r.get("id", ""),
        "display_name": r.get("display_name", ""),
        "works_count": r.get("works_count", 0),
        "h_index": r.get("summary_stats", {}).get("h_index", 0),
        "affiliations": affiliations,
        "topics": topics,
        "source": "openalex",
    }


def _format_s2_author_candidate(r: dict) -> dict:
    """Shape a raw Semantic Scholar author dict for the frontend."""
    affiliations = [
        {"name": aff, "year_range": None}
        for aff in (r.get("affiliations") or [])[:3]
        if aff
    ]
    return {
        "id": f"S2:{r.get('authorId', '')}",
        "display_name": r.get("name", ""),
        "works_count": r.get("paperCount", 0),
        "h_index": r.get("hIndex", 0),
        "affiliations": affiliations,
        "topics": [],
        "source": "semantic_scholar",
    }


def _format_oa_authorship_candidate(authorship: dict) -> dict:
    """Shape an OpenAlex authorship entry (from a work) for the frontend."""
    author = authorship.get("author") or {}
    institutions = authorship.get("institutions") or []
    affiliations = [
        {"name": inst.get("display_name", ""), "year_range": None}
        for inst in institutions[:3]
        if inst.get("display_name")
    ]
    return {
        "id": author.get("id", ""),
        "display_name": author.get("display_name", ""),
        "works_count": 0,
        "h_index": 0,
        "affiliations": affiliations,
        "topics": [],
        "source": "openalex",
    }


@router.get("/author-search")
async def search_authors_endpoint(
    query: str = Query(..., min_length=2),
    uid: str = Depends(get_current_user),
) -> list[dict]:
    """Search OpenAlex and Semantic Scholar in parallel for author candidates."""
    _check_rate_limit(_author_search_timestamps, uid, _SEARCH_RATE_LIMIT)

    from app.services import openalex as openalex_svc
    from app.services import semantic_scholar as s2_svc

    q = query.strip()

    oa_raw, s2_raw = await asyncio.gather(
        openalex_svc.search_authors(q),
        s2_svc.search_authors(q),
        return_exceptions=True,
    )

    candidates: list[dict] = []

    if isinstance(oa_raw, list):
        candidates.extend(_format_author_candidate(r) for r in oa_raw)
    else:
        logger.warning("OpenAlex author search failed: %s", oa_raw)

    if isinstance(s2_raw, list):
        candidates.extend(_format_s2_author_candidate(r) for r in s2_raw)
    else:
        logger.warning("S2 author search failed: %s", s2_raw)

    return candidates


@router.get("/paper-authors")
async def get_paper_authors_endpoint(
    doi: str = Query(..., min_length=5),
    uid: str = Depends(get_current_user),
) -> dict:
    """Look up a paper by DOI and return its authors as AuthorCandidate records.
    Tries Semantic Scholar first, falls back to OpenAlex for broader coverage."""
    _check_rate_limit(_paper_authors_timestamps, uid, _PAPER_AUTHORS_RATE_LIMIT)

    from app.services import openalex as openalex_svc
    from app.services import semantic_scholar as s2_svc

    paper = await s2_svc.get_paper_with_authors(doi)
    if paper is not None:
        authors = [
            _format_s2_author_candidate(a)
            for a in (paper.get("authors") or [])
            if a.get("authorId")
        ]
        return {
            "paper_title": paper.get("title") or "Unknown title",
            "paper_year": paper.get("year"),
            "authors": authors,
        }

    oa_work = await openalex_svc.get_work_by_doi(doi)
    if oa_work is not None:
        authorships = [
            a for a in (oa_work.get("authorships") or [])
            if (a.get("author") or {}).get("id")
        ]
        author_ids = [a["author"]["id"] for a in authorships]
        full_profiles = await openalex_svc.get_authors_by_ids(author_ids)
        profile_by_id = {p["id"]: p for p in full_profiles}
        authors = [
            _format_author_candidate(profile_by_id[a["author"]["id"]])
            if a["author"]["id"] in profile_by_id
            else _format_oa_authorship_candidate(a)
            for a in authorships
        ]
        return {
            "paper_title": oa_work.get("title") or "Unknown title",
            "paper_year": oa_work.get("publication_year"),
            "authors": authors,
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Paper not found on Semantic Scholar or OpenAlex. Check the DOI and try again.",
    )


@router.post("/import")
async def import_works_by_author(
    body: ImportByAuthorRequest,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict:
    """Bulk-import all works by an author (OpenAlex, S2, INSPIRE-HEP, or DBLP)."""
    from app.services import dblp as dblp_svc
    from app.services import inspire_hep as inspire_svc
    from app.services import openalex as openalex_svc
    from app.services import semantic_scholar as s2_svc

    # Enforce single linked-author policy.
    user_ref = db.collection("users").document(uid)
    user_snap = user_ref.get()
    user_data = user_snap.to_dict() or {} if user_snap.exists else {}

    # Rate-limit bulk imports to prevent Firestore write floods.
    enforce_cooldown(
        user_data, "last_import_at", _IMPORT_COOLDOWN,
        "You've run an import recently. Please wait before importing again.",
        fallback_field="created_at",
    )

    # Normalise IDs for comparison (strip full URL prefix if present).
    def _short_id(author_id: str) -> str:
        prefix = "https://openalex.org/"
        return author_id[len(prefix):] if author_id.startswith(prefix) else author_id

    incoming_short = _short_id(body.author_id)
    stored_id: str | None = user_data.get("linked_author_id")
    stored_name: str | None = user_data.get("linked_author_name")

    # Build the full set of already-linked author IDs (primary + additional).
    additional: list[dict] = user_data.get("additional_linked_authors") or []
    all_linked_short: set[str] = set()
    if stored_id:
        all_linked_short.add(_short_id(stored_id))
    for entry in additional:
        if entry.get("id"):
            all_linked_short.add(_short_id(entry["id"]))

    is_new_author = bool(stored_id) and incoming_short not in all_linked_short

    if is_new_author and not body.confirm_merge:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "merge_required",
                "existing_author_name": stored_name or stored_id,
            },
        )

    if body.source == "semantic_scholar":
        raw_works = await s2_svc.get_works_by_author(body.author_id)
    elif body.source == "inspire":
        raw_works = await inspire_svc.get_works_by_author(body.author_id)
    elif body.source == "dblp":
        raw_works = await dblp_svc.get_works_by_author(body.author_id)
    else:
        raw_works = await openalex_svc.get_works_by_author(body.author_id)

    # If the frontend didn't supply the author's display name, recover it from
    # the authorships data on the fetched works.  Without a stored name the
    # author-presence check on future manual add_work calls is silently skipped.
    author_display_name: str | None = body.author_name or None
    if not author_display_name:
        for raw in raw_works[:20]:
            for authorship in raw.get("authorships", []):
                author_info = authorship.get("author", {})
                if _short_id(author_info.get("id", "")) == incoming_short:
                    author_display_name = author_info.get("display_name", "").strip() or None
                    break
            if author_display_name:
                break
        if author_display_name:
            logger.info(
                "Resolved display name for author %s from works: %s",
                incoming_short, author_display_name,
            )
        elif body.source == "semantic_scholar":
            author_display_name = await s2_svc.get_author_name(incoming_short)
            if author_display_name:
                logger.info(
                    "Resolved display name for S2 author %s via profile lookup: %s",
                    incoming_short, author_display_name,
                )
            else:
                logger.warning(
                    "Could not resolve display name for author %s — author-presence check will be inactive.",
                    incoming_short,
                )
        else:
            logger.warning(
                "Could not resolve display name for author %s — author-presence check will be inactive.",
                incoming_short,
            )

    # ── Cross-source coverage boost ──────────────────────────────────────────
    # Each requested extra source is searched by author name, all at once.
    # A candidate's works are merged only if at least one DOI overlaps the
    # primary source, so a same-name researcher can't pollute the import.
    if author_display_name and body.extra_sources:
        raw_works = raw_works + await _gather_cross_source_works(
            primary_source=body.source,
            extra_sources=body.extra_sources,
            author_name=author_display_name,
            primary_works=raw_works,
        )

    works_ref = user_ref.collection("trackedWorks")
    # Case-insensitive: older imports stored mixed-case DOI document IDs.
    existing_ids = {doc.id.lower() for doc in works_ref.stream()}
    dismissed = {d.lower() for d in (user_data.get("dismissed_work_ids") or [])}

    # Cap total tracked works at 500 per user to prevent runaway Firestore
    # writes and excessive citation-check workload.
    remaining_capacity = max(0, _MAX_TRACKED_WORKS - len(existing_ids))

    imported = 0
    skipped = 0
    now = datetime.now(tz=timezone.utc)
    batch = db.batch()
    pending = 0

    # Keep one version per (near-)identical title, preferring journal or
    # proceedings DOIs over arXiv preprints.
    for raw in dedupe_works_by_title(raw_works):
        doi = normalize_doi(raw.get("doi"))
        work_id = doi_to_work_id(doi)  # type: ignore[arg-type]
        if work_id in existing_ids or work_id in dismissed or imported >= remaining_capacity:
            skipped += 1
            continue

        batch.set(works_ref.document(work_id), {
            "doi": doi,
            "openalex_id": raw.get("id"),
            "title": raw.get("title") or "Untitled",
            "authors": [
                a.get("author", {}).get("display_name", "").strip()
                for a in raw.get("authorships", [])
                if a.get("author", {}).get("display_name")
            ],
            "year": raw.get("publication_year"),
            "venue": extract_venue(raw),
            "work_type": raw.get("type"),
            "topics": extract_topics(raw),
            "added_at": now,
            "last_checked_at": None,
            "openalex_citation_count": raw.get("cited_by_count"),
        })
        pending += 1
        if pending == 500:  # Firestore batch limit
            batch.commit()
            batch, pending = db.batch(), 0
        existing_ids.add(work_id)
        imported += 1

    if pending:
        batch.commit()

    # Persist author linkage and the import timestamp in one write.
    user_updates: dict = {"last_import_at": now}
    if not stored_id:
        user_updates["linked_author_id"] = incoming_short
        if author_display_name:
            user_updates["linked_author_name"] = author_display_name
        logger.info("Linked uid=%s to author %s (%s)", uid, incoming_short, author_display_name)
    elif is_new_author and body.confirm_merge:
        user_updates["additional_linked_authors"] = additional + [
            {"id": incoming_short, "name": author_display_name}
        ]
        logger.info(
            "Merged author %s (%s) into uid=%s additional linked authors",
            incoming_short, author_display_name, uid,
        )
    user_ref.set(user_updates, merge=True)

    logger.info("Bulk import: %d imported, %d skipped for uid=%s", imported, skipped, uid)
    return {"imported": imported, "skipped": skipped}


_MAX_TRACKED_WORKS = 500


def _doi_set(works: list[dict]) -> set[str]:
    return {d for d in (normalize_doi(w.get("doi")) for w in works) if d}


async def _gather_cross_source_works(
    primary_source: str,
    extra_sources: list[str],
    author_name: str,
    primary_works: list[dict],
) -> list[dict]:
    """Search every requested extra source concurrently; return merged works."""
    from app.services import dblp as dblp_svc
    from app.services import inspire_hep as inspire_svc
    from app.services import nasa_ads as ads_svc
    from app.services import openalex as openalex_svc
    from app.services import pubmed as pubmed_svc
    from app.services import semantic_scholar as s2_svc

    # source -> (service, candidate name key, candidate id key, candidates to try)
    adapters = {
        "openalex": (openalex_svc, "display_name", "id", 3),
        "semantic_scholar": (s2_svc, "name", "authorId", 3),
        "pubmed": (pubmed_svc, "name", "authorId", 1),
        "nasa_ads": (ads_svc, "name", "authorId", 1),
        "inspire": (inspire_svc, "name", "authorId", 3),
        "dblp": (dblp_svc, "name", "authorId", 3),
    }
    primary_dois = _doi_set(primary_works)

    async def fetch(source: str) -> list[dict]:
        svc, name_key, id_key, limit = adapters[source]
        try:
            candidates = await svc.search_authors(author_name)
            for cand in candidates[:limit]:
                if not _names_match(cand.get(name_key, ""), author_name):
                    continue
                extra = await svc.get_works_by_author(cand[id_key])
                overlap = primary_dois & _doi_set(extra or [])
                if overlap:
                    logger.info(
                        "Cross-source: merged %d %s works for '%s' (%d DOI(s) overlap)",
                        len(extra), source, author_name, len(overlap),
                    )
                    return extra
                return []  # first name match decides; don't try weaker matches
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s cross-source fetch failed for '%s': %s; skipping",
                source, author_name, exc,
            )
        return []

    sources = [
        s for s in dict.fromkeys(extra_sources)
        if s in adapters and s != primary_source
        # OpenAlex is only an "extra" when the primary was Semantic Scholar.
        and not (s == "openalex" and primary_source != "semantic_scholar")
    ]
    results = await asyncio.gather(*(fetch(s) for s in sources))
    return [w for works in results for w in works]


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work(
    work_id: str,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> None:
    """Remove a tracked work and all its notifications.

    The work is also recorded as dismissed so the weekly publication sync
    doesn't quietly add it back. Plain ``def``: FastAPI runs it in a worker
    thread, so the blocking Firestore calls don't stall the event loop.
    """
    from firebase_admin import firestore

    from app.services.citation_service import _commit_in_batches

    user_ref = db.collection("users").document(uid)
    ref = user_ref.collection("trackedWorks").document(work_id)
    if not ref.get().exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracked work not found.",
        )

    notif_refs = [
        ndoc.reference
        for ndoc in user_ref.collection("notifications").where("cited_work_id", "==", work_id).stream()
    ]
    _commit_in_batches(db, [("delete", r, None) for r in [ref, *notif_refs]])
    user_ref.set({"dismissed_work_ids": firestore.ArrayUnion([work_id.lower()])}, merge=True)

    logger.info(
        "Deleted tracked work %s and %d notification(s) for uid=%s",
        work_id, len(notif_refs), uid,
    )


@router.get("", response_model=list[TrackedWork])
def list_works(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> list[TrackedWork]:
    """Return all tracked works with citation counts, sorted by publication year descending."""
    thirty_days_ago = (datetime.now(tz=timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_year = int(thirty_days_ago[:4])
    total_counts: defaultdict[str, int] = defaultdict(int)
    recent_counts: defaultdict[str, int] = defaultdict(int)

    # Only the three fields we count with; avoids pulling whole documents.
    notifs = (
        db.collection("users").document(uid).collection("notifications")
        .select(["cited_work_id", "citing_publication_date", "citing_year"])
    )
    for ndoc in notifs.stream():
        ndata = ndoc.to_dict() or {}
        work_id = ndata.get("cited_work_id", "")
        if not work_id:
            continue
        total_counts[work_id] += 1
        # Count as "recent" only when the citing paper was actually published
        # within the last 30 days (mirrors the discovery and display filters).
        pub_date: str = ndata.get("citing_publication_date") or ""
        pub_year: int = ndata.get("citing_year") or 0
        if pub_date >= thirty_days_ago or (not pub_date and pub_year >= cutoff_year):
            recent_counts[work_id] += 1

    works: list[TrackedWork] = []
    for doc in db.collection("users").document(uid).collection("trackedWorks").stream():
        work = _doc_to_tracked_work(doc.id, doc.to_dict() or {})
        work.citation_count = total_counts.get(doc.id, 0)
        work.new_citations_30d = recent_counts.get(doc.id, 0)
        works.append(work)

    # Sort by publication year descending; works without a year go last.
    works.sort(key=lambda w: (w.year is not None, w.year or 0), reverse=True)
    return works

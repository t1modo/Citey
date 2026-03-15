import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_current_user
from app.firebase_client import get_db
from app.models import AddWorkRequest, ImportByAuthorRequest, TrackedWork
from app.services.crossref import resolve_doi

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/works", tags=["works"])


def _name_tokens(name: str) -> list[str]:
    """Lowercase, replace separators with spaces, return non-empty tokens."""
    return [t for t in re.sub(r"[^a-z\s]", "", name.lower().replace(".", " ").replace("-", " ")).split() if t]


def _names_match(a: str, b: str) -> bool:
    """
    Fuzzy name match that tolerates:
      - Case differences
      - Middle name omission: "Timothy Do" matches "Timothy Khang Do"
      - First initials: "T. Do" matches "Timothy Do"
      - Reversed order is NOT allowed — last name must match last name.
    """
    a_tok = _name_tokens(a)
    b_tok = _name_tokens(b)
    if not a_tok or not b_tok:
        return False
    if a_tok == b_tok:
        return True
    # Last token (family name) must match exactly.
    if a_tok[-1] != b_tok[-1]:
        return False
    # Compare given-name tokens: take the shorter list and try to match
    # each token against tokens in the longer list in order, allowing
    # a single-char token to match any longer token that starts with it.
    short_given = a_tok[:-1] if len(a_tok) <= len(b_tok) else b_tok[:-1]
    long_given = a_tok[:-1] if len(a_tok) > len(b_tok) else b_tok[:-1]
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
        added_at=_to_dt(data.get("added_at")),
        last_checked_at=_to_dt(data.get("last_checked_at")),
        s2_citation_count=data.get("s2_citation_count"),
        openalex_citation_count=data.get("openalex_citation_count"),
    )


@router.post("/", response_model=TrackedWork, status_code=status.HTTP_201_CREATED)
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
        linked_name: str | None = user_data.get("linked_author_name")
        if linked_name:
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
    # without a separate lookup step.
    if not work_info.get("openalex_id"):
        from app.services.openalex import get_work_by_doi as _oa_lookup
        oa_raw = await _oa_lookup(work_info["doi"])
        if oa_raw:
            work_info["openalex_id"] = oa_raw.get("id")
            work_info["openalex_citation_count"] = oa_raw.get("cited_by_count")
            logger.info("Resolved OpenAlex ID for %s: %s", work_info["doi"], work_info["openalex_id"])

    # Sanitize the DOI to form a valid Firestore document ID.
    work_id = work_info["doi"].replace("/", "__")

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
        "added_at": now,
        "last_checked_at": None,
        "openalex_citation_count": work_info.get("openalex_citation_count"),
    }
    ref.set(doc_data)
    logger.info("Added tracked work %s for uid=%s", work_id, uid)

    return _doc_to_tracked_work(work_id, doc_data)


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(
    work_id: str,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> None:
    """Remove a tracked work and all its notifications from the user's subcollection."""
    user_ref = db.collection("users").document(uid)
    ref = user_ref.collection("trackedWorks").document(work_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracked work not found.",
        )
    ref.delete()

    # Cascade-delete every notification that was triggered by this work.
    notifs_ref = user_ref.collection("notifications")
    for ndoc in notifs_ref.where("cited_work_id", "==", work_id).stream():
        ndoc.reference.delete()

    logger.info("Deleted tracked work %s and its notifications for uid=%s", work_id, uid)


@router.get("/author-search")
async def search_authors_endpoint(
    query: str = Query(..., min_length=2),
    uid: str = Depends(get_current_user),
) -> list[dict]:
    """Search OpenAlex for author candidates matching the given name query."""
    from app.services import openalex as openalex_svc

    results = await openalex_svc.search_authors(query)
    return [
        {
            "id": r.get("id", ""),
            "display_name": r.get("display_name", ""),
            "works_count": r.get("works_count", 0),
            "affiliations": [
                a.get("institution", {}).get("display_name", "")
                for a in r.get("affiliations", [])[:2]
                if a.get("institution", {}).get("display_name")
            ],
        }
        for r in results
    ]


@router.post("/import")
async def import_works_by_author(
    body: ImportByAuthorRequest,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict:
    """Bulk-import all works by an OpenAlex author into the user's tracked works."""
    from app.services import openalex as openalex_svc

    # Enforce single linked-author policy.
    user_ref = db.collection("users").document(uid)
    user_snap = user_ref.get()
    user_data = user_snap.to_dict() or {} if user_snap.exists else {}

    # Normalise IDs for comparison (strip full URL prefix if present).
    def _short_id(author_id: str) -> str:
        prefix = "https://openalex.org/"
        return author_id[len(prefix):] if author_id.startswith(prefix) else author_id

    incoming_short = _short_id(body.author_id)
    stored_id: str | None = user_data.get("linked_author_id")
    stored_name: str | None = user_data.get("linked_author_name")

    if stored_id and _short_id(stored_id) != incoming_short:
        detail = (
            f"This account is already linked to \"{stored_name or stored_id}\". "
            "Each account may only import works for one author."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    raw_works = await openalex_svc.get_works_by_author(body.author_id)

    # Deduplicate by title: for papers published in multiple venues (e.g. arXiv
    # preprint + conference proceedings), keep only the best version per title.
    # Uses fuzzy matching (SequenceMatcher ratio >= 0.85) to catch near-duplicate
    # titles where a word or two changed between preprint and final version.
    # "Best" means non-arXiv first; among ties, the first returned by OpenAlex.
    import re
    from difflib import SequenceMatcher

    def _is_arxiv(doi: str | None) -> bool:
        return bool(doi and doi.lower().startswith("10.48550/arxiv"))

    def _strip_doi(doi: str | None) -> str | None:
        if not doi:
            return doi
        for prefix in ("https://doi.org/", "http://doi.org/"):
            if doi.startswith(prefix):
                return doi[len(prefix):]
        return doi

    def _norm_title(title: str) -> str:
        """Lowercase and strip punctuation for fuzzy comparison."""
        return re.sub(r"[^a-z0-9\s]", "", title.lower()).strip()

    def _is_near_duplicate(a: str, b: str) -> bool:
        return SequenceMatcher(None, a, b).ratio() >= 0.85

    seen_titles: dict[str, dict] = {}  # norm_title -> raw work dict
    for raw in raw_works:
        doi_raw = _strip_doi(raw.get("doi"))
        if not doi_raw:
            continue
        norm = _norm_title(raw.get("title") or "")
        if not norm:
            continue

        # Check for an existing entry that is a near-duplicate.
        matched_key = next(
            (k for k in seen_titles if _is_near_duplicate(norm, k)), None
        )
        if matched_key is None:
            seen_titles[norm] = raw
        else:
            # Keep the non-arXiv (proceedings/journal) version.
            stored_doi = _strip_doi(seen_titles[matched_key].get("doi"))
            if _is_arxiv(stored_doi) and not _is_arxiv(doi_raw):
                del seen_titles[matched_key]
                seen_titles[norm] = raw

    works_ref = db.collection("users").document(uid).collection("trackedWorks")
    existing_ids = {doc.id for doc in works_ref.stream()}

    imported = 0
    skipped = 0
    now = datetime.now(tz=timezone.utc)

    for raw in seen_titles.values():
        doi: str | None = _strip_doi(raw.get("doi"))

        if not doi:
            skipped += 1
            continue

        work_id = doi.replace("/", "__")
        if work_id in existing_ids:
            skipped += 1
            continue

        title: str = raw.get("title") or "Untitled"
        authors: list[str] = [
            a.get("author", {}).get("display_name", "").strip()
            for a in raw.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        year: int | None = raw.get("publication_year")
        openalex_id: str | None = raw.get("id")
        openalex_citation_count: int | None = raw.get("cited_by_count")

        works_ref.document(work_id).set({
            "doi": doi,
            "openalex_id": openalex_id,
            "title": title,
            "authors": authors,
            "year": year,
            "added_at": now,
            "last_checked_at": None,
            "openalex_citation_count": openalex_citation_count,
        })
        existing_ids.add(work_id)
        imported += 1

    # Lock the account to this author on first successful import.
    if not stored_id:
        link_data: dict = {"linked_author_id": incoming_short}
        if body.author_name:
            link_data["linked_author_name"] = body.author_name
        user_ref.set(link_data, merge=True)
        logger.info("Linked uid=%s to author %s (%s)", uid, incoming_short, body.author_name)

    logger.info("Bulk import: %d imported, %d skipped for uid=%s", imported, skipped, uid)
    return {"imported": imported, "skipped": skipped}


@router.get("/", response_model=list[TrackedWork])
async def list_works(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> list[TrackedWork]:
    """Return all tracked works with citation counts, sorted by publication year descending."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
    total_counts: defaultdict[str, int] = defaultdict(int)
    recent_counts: defaultdict[str, int] = defaultdict(int)

    for ndoc in db.collection("users").document(uid).collection("notifications").stream():
        ndata = ndoc.to_dict() or {}
        work_id = ndata.get("cited_work_id", "")
        if not work_id:
            continue
        total_counts[work_id] += 1
        created_at = ndata.get("created_at")
        if created_at is not None:
            if hasattr(created_at, "tzinfo") and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at >= cutoff:
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

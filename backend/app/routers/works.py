import asyncio
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
from app.services.openalex import extract_topics, extract_venue

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
            logger.info("Resolved OpenAlex ID for %s: %s", work_info["doi"], work_info["openalex_id"])

    # Normalise DOI to lowercase for consistent Firestore document IDs.
    # DOIs are case-insensitive; mixing cases creates phantom duplicates.
    work_info["doi"] = work_info["doi"].lower()
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
        "venue": work_info.get("venue"),
        "work_type": work_info.get("work_type"),
        "topics": work_info.get("topics", []),
        "added_at": now,
        "last_checked_at": None,
        "openalex_citation_count": work_info.get("openalex_citation_count"),
    }
    ref.set(doc_data)
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
    external = r.get("externalIds") or {}
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
        "topics": [],  # S2 author search doesn't return topic data
        "source": "semantic_scholar",
    }


@router.get("/author-search")
async def search_authors_endpoint(
    query: str = Query(..., min_length=2),
    uid: str = Depends(get_current_user),
) -> list[dict]:
    """Search OpenAlex and Semantic Scholar in parallel for author candidates."""
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
    """Look up a paper by DOI on Semantic Scholar and return its authors as
    AuthorCandidate records.  Used for the 'find by paper DOI' import mode."""
    from app.services import semantic_scholar as s2_svc

    paper = await s2_svc.get_paper_with_authors(doi)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found on Semantic Scholar. Check the DOI and try again.",
        )

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


@router.post("/import")
async def import_works_by_author(
    body: ImportByAuthorRequest,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict:
    """Bulk-import all works by an author (OpenAlex, S2, INSPIRE-HEP, or DBLP)."""
    from app.services import dblp as dblp_svc
    from app.services import inspire_hep as inspire_svc
    from app.services import nasa_ads as ads_svc
    from app.services import openalex as openalex_svc
    from app.services import pubmed as pubmed_svc
    from app.services import semantic_scholar as s2_svc

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

    # ── Cross-source coverage boost ──────────────────────────────────────────
    # After fetching from the primary source, search the complementary source
    # by author name and merge their works in.  This catches papers indexed in
    # one source but not the other (e.g. S2 misses some conference proceedings
    # that OpenAlex has, and vice versa).
    #
    # Safety: we require at least one DOI to overlap between the primary works
    # and the candidate's works before merging, so a same-name researcher in
    # the other source doesn't pollute the import.
    if author_display_name:
        primary_dois: set[str] = set()
        for r in raw_works:
            d = _strip_doi(r.get("doi"))
            if d:
                primary_dois.add(d.lower())

        try:
            if body.source == "semantic_scholar":
                # Primary was S2 — also pull from OpenAlex
                oa_candidates = await openalex_svc.search_authors(author_display_name)
                for c in oa_candidates[:3]:
                    if _names_match(c.get("display_name", ""), author_display_name):
                        oa_extra = await openalex_svc.get_works_by_author(c["id"])
                        if oa_extra:
                            extra_dois: set[str] = set()
                            for r in oa_extra:
                                d = _strip_doi(r.get("doi"))
                                if d:
                                    extra_dois.add(d.lower())
                            overlap = primary_dois & extra_dois
                            if not primary_dois or overlap:
                                raw_works = raw_works + oa_extra
                                logger.info(
                                    "Cross-source: merged %d OpenAlex works for '%s' "
                                    "(%d DOI(s) overlap)",
                                    len(oa_extra), author_display_name, len(overlap),
                                )
                        break
            else:
                # Primary was OpenAlex — also pull from S2
                s2_candidates = await s2_svc.search_authors(author_display_name)
                for c in s2_candidates[:3]:
                    if _names_match(c.get("name", ""), author_display_name):
                        s2_extra = await s2_svc.get_works_by_author(c["authorId"])
                        if s2_extra:
                            extra_dois = set()
                            for r in s2_extra:
                                d = _strip_doi(r.get("doi"))
                                if d:
                                    extra_dois.add(d.lower())
                            overlap = primary_dois & extra_dois
                            if not primary_dois or overlap:
                                raw_works = raw_works + s2_extra
                                logger.info(
                                    "Cross-source: merged %d S2 works for '%s' "
                                    "(%d DOI(s) overlap)",
                                    len(s2_extra), author_display_name, len(overlap),
                                )
                        break
        except Exception as exc:
            logger.warning(
                "Cross-source fetch failed for '%s': %s — continuing with primary source only",
                author_display_name, exc,
            )

    # ── PubMed cross-source boost ────────────────────────────────────────────
    # Always attempted as a third source (biomedical coverage that neither OA
    # nor S2 captures reliably).  Re-computes the DOI set to include any works
    # already merged in the OA↔S2 pass above.
    if author_display_name:
        current_dois: set[str] = set()
        for r in raw_works:
            d = _strip_doi(r.get("doi"))
            if d:
                current_dois.add(d.lower())
        try:
            pm_candidates = await pubmed_svc.search_authors(author_display_name)
            for c in pm_candidates[:1]:
                if _names_match(c.get("name", ""), author_display_name):
                    pm_extra = await pubmed_svc.get_works_by_author(c["authorId"])
                    if pm_extra:
                        pm_dois: set[str] = set()
                        for r in pm_extra:
                            d = _strip_doi(r.get("doi"))
                            if d:
                                pm_dois.add(d.lower())
                        overlap = current_dois & pm_dois
                        if not current_dois or overlap:
                            raw_works = raw_works + pm_extra
                            logger.info(
                                "Cross-source: merged %d PubMed works for '%s' "
                                "(%d DOI(s) overlap)",
                                len(pm_extra), author_display_name, len(overlap),
                            )
        except Exception as exc:
            logger.warning(
                "PubMed cross-source fetch failed for '%s': %s — skipping",
                author_display_name, exc,
            )

    # ── NASA ADS cross-source boost ──────────────────────────────────────────
    # Astrophysics / space-science literature that OA, S2, and PubMed all miss.
    # Recomputes the DOI set to include any works already merged above.
    if author_display_name:
        current_dois_ads: set[str] = set()
        for r in raw_works:
            d = _strip_doi(r.get("doi"))
            if d:
                current_dois_ads.add(d.lower())
        try:
            ads_candidates = await ads_svc.search_authors(author_display_name)
            for c in ads_candidates[:1]:
                if _names_match(c.get("name", ""), author_display_name):
                    ads_extra = await ads_svc.get_works_by_author(c["authorId"])
                    if ads_extra:
                        ads_dois: set[str] = set()
                        for r in ads_extra:
                            d = _strip_doi(r.get("doi"))
                            if d:
                                ads_dois.add(d.lower())
                        overlap = current_dois_ads & ads_dois
                        if not current_dois_ads or overlap:
                            raw_works = raw_works + ads_extra
                            logger.info(
                                "Cross-source: merged %d NASA ADS works for '%s' "
                                "(%d DOI(s) overlap)",
                                len(ads_extra), author_display_name, len(overlap),
                            )
        except Exception as exc:
            logger.warning(
                "NASA ADS cross-source fetch failed for '%s': %s — skipping",
                author_display_name, exc,
            )

    # ── INSPIRE-HEP cross-source boost ──────────────────────────────────────
    # HEP, accelerator physics, and JACoW/CERN conference proceedings —
    # the only automated path for papers from those venues.
    # Uses a two-step author-search → works-by-id pattern (more precise than
    # a bare name search against the literature index).
    if author_display_name and body.source != "inspire":
        current_dois_inspire: set[str] = set()
        for r in raw_works:
            d = _strip_doi(r.get("doi"))
            if d:
                current_dois_inspire.add(d.lower())
        try:
            inspire_candidates = await inspire_svc.search_authors(author_display_name)
            for c in inspire_candidates[:3]:
                if _names_match(c.get("name", ""), author_display_name):
                    inspire_extra = await inspire_svc.get_works_by_author(c["authorId"])
                    if inspire_extra:
                        inspire_dois: set[str] = set()
                        for r in inspire_extra:
                            d = _strip_doi(r.get("doi"))
                            if d:
                                inspire_dois.add(d.lower())
                        overlap = current_dois_inspire & inspire_dois
                        if not current_dois_inspire or overlap:
                            raw_works = raw_works + inspire_extra
                            logger.info(
                                "Cross-source: merged %d INSPIRE-HEP works for '%s' "
                                "(%d DOI(s) overlap)",
                                len(inspire_extra), author_display_name, len(overlap),
                            )
                    break
        except Exception as exc:
            logger.warning(
                "INSPIRE-HEP cross-source fetch failed for '%s': %s — skipping",
                author_display_name, exc,
            )

    # ── DBLP cross-source boost ──────────────────────────────────────────────
    # CS conference and journal papers — virtually complete ACM / IEEE coverage.
    # Uses a two-step author-search (returns PID) → publication-search pattern
    # so results are scoped to exactly one person, not a name-based full-text
    # match that would flood the results with same-name researchers.
    if author_display_name and body.source != "dblp":
        current_dois_dblp: set[str] = set()
        for r in raw_works:
            d = _strip_doi(r.get("doi"))
            if d:
                current_dois_dblp.add(d.lower())
        try:
            dblp_candidates = await dblp_svc.search_authors(author_display_name)
            for c in dblp_candidates[:3]:
                if _names_match(c.get("name", ""), author_display_name):
                    dblp_extra = await dblp_svc.get_works_by_author(c["authorId"])
                    if dblp_extra:
                        dblp_dois: set[str] = set()
                        for r in dblp_extra:
                            d = _strip_doi(r.get("doi"))
                            if d:
                                dblp_dois.add(d.lower())
                        overlap = current_dois_dblp & dblp_dois
                        if not current_dois_dblp or overlap:
                            raw_works = raw_works + dblp_extra
                            logger.info(
                                "Cross-source: merged %d DBLP works for '%s' "
                                "(%d DOI(s) overlap)",
                                len(dblp_extra), author_display_name, len(overlap),
                            )
                    break
        except Exception as exc:
            logger.warning(
                "DBLP cross-source fetch failed for '%s': %s — skipping",
                author_display_name, exc,
            )

    seen_titles: dict[str, dict] = {}  # norm_title -> raw work dict
    for raw in raw_works:
        doi_raw = _strip_doi(raw.get("doi"))
        if not doi_raw:
            continue
        doi_raw = doi_raw.lower()  # Normalise to lowercase — DOIs are case-insensitive
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
            "venue": extract_venue(raw),
            "work_type": raw.get("type"),
            "topics": extract_topics(raw),
            "added_at": now,
            "last_checked_at": None,
            "openalex_citation_count": openalex_citation_count,
        })
        existing_ids.add(work_id)
        imported += 1

    # Persist author linkage after a successful import.
    if not stored_id:
        # First-ever import: set the primary linked author.
        link_data: dict = {"linked_author_id": incoming_short}
        if author_display_name:
            link_data["linked_author_name"] = author_display_name
        user_ref.set(link_data, merge=True)
        logger.info("Linked uid=%s to author %s (%s)", uid, incoming_short, author_display_name)
    elif is_new_author and body.confirm_merge:
        # Merge-confirmed: append to additional_linked_authors.
        new_entry = {"id": incoming_short, "name": author_display_name}
        updated_additional = additional + [new_entry]
        user_ref.set({"additional_linked_authors": updated_additional}, merge=True)
        logger.info(
            "Merged author %s (%s) into uid=%s additional linked authors",
            incoming_short, author_display_name, uid,
        )

    logger.info("Bulk import: %d imported, %d skipped for uid=%s", imported, skipped, uid)
    return {"imported": imported, "skipped": skipped}


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


@router.get("", response_model=list[TrackedWork])
async def list_works(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> list[TrackedWork]:
    """Return all tracked works with citation counts, sorted by publication year descending."""
    thirty_days_ago = (datetime.now(tz=timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_year = int(thirty_days_ago[:4])
    total_counts: defaultdict[str, int] = defaultdict(int)
    recent_counts: defaultdict[str, int] = defaultdict(int)

    for ndoc in db.collection("users").document(uid).collection("notifications").stream():
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

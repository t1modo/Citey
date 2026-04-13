"""
INSPIRE-HEP API client.

Used as a cross-source coverage boost for high-energy physics, accelerator
physics, nuclear physics, and related physical-sciences literature — the
canonical database for papers from JACoW, CERN, SLAC, Fermilab, and similar
venues that are systematically absent from OpenAlex, Semantic Scholar, and
even NASA ADS.

No API key required — the INSPIRE REST API is free and open.

Docs: https://github.com/inspirehep/rest-api-doc
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.services.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

_author_search_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=300)
_works_by_author_cache: AsyncTTLCache = AsyncTTLCache(maxsize=100, ttl=3600)

_BASE_URL = "https://inspirehep.net/api"
_HEADERS = {
    "User-Agent": "Citey/0.1 (mailto:support@citey.app)",
    "Accept": "application/json",
}
_PAGE_SIZE = 25    # INSPIRE's default; safe for all accounts
_MAX_RESULTS = 500  # Hard cap to prevent runaway pagination
_MAX_RETRIES = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _inspire_to_first_last(inspire_name: str) -> str:
    """
    Convert INSPIRE author name format "Last, First" → "First Last".
    Leaves names without a comma unchanged.
    """
    if "," in inspire_name:
        last, _, first = inspire_name.partition(",")
        return f"{first.strip()} {last.strip()}"
    return inspire_name.strip()


def _first_last_to_inspire(name: str) -> str:
    """
    Convert "First [Middle] Last" → "Last, First" for INSPIRE author queries.
    """
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    context: str = "",
) -> httpx.Response | None:
    """GET with automatic 429 retry and exponential back-off."""
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("INSPIRE request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "INSPIRE rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error(
        "INSPIRE rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context
    )
    return None


def _normalize_work(record: dict) -> dict | None:
    """
    Convert a single INSPIRE literature record to an OpenAlex-compatible dict.
    Returns ``None`` if the record carries no DOI.
    """
    metadata = record.get("metadata", {})

    # DOI: stored as a list of {"value": "..."} dicts
    doi: str | None = None
    for doi_entry in metadata.get("dois", []):
        raw = doi_entry.get("value", "").strip()
        if raw:
            doi = raw
            break

    # INSPIRE records for conference papers often lack a DOI but have an
    # arXiv e-print — derive an arXiv DOI so the dedup logic can work.
    if not doi:
        for eprint in metadata.get("arxiv_eprints", []):
            val = eprint.get("value", "").strip()
            if val:
                doi = f"10.48550/arXiv.{val}"
                break

    if not doi:
        return None

    if not doi.startswith("http"):
        doi = f"https://doi.org/{doi}"

    # Title: list of {"title": "..."} dicts
    title = ""
    for t_entry in metadata.get("titles", []):
        candidate = t_entry.get("title", "").strip()
        if candidate:
            title = candidate
            break

    # Year: prefer earliest_date, fall back to imprint.date
    year: int | None = None
    for date_str in (
        metadata.get("earliest_date", ""),
        (metadata.get("imprint") or {}).get("date", ""),
    ):
        if date_str:
            try:
                year = int(str(date_str)[:4])
                break
            except (ValueError, TypeError):
                continue

    # Authors: list of {"full_name": "Last, First"} dicts
    authorships = []
    for author in metadata.get("authors", []):
        raw_name = author.get("full_name", "").strip()
        if raw_name:
            display = _inspire_to_first_last(raw_name)
            authorships.append({"author": {"id": "", "display_name": display}})

    record_id = str(record.get("id", ""))

    return {
        "doi": doi,
        "title": title,
        "publication_year": year,
        "id": f"inspire:{record_id}",
        "cited_by_count": 0,
        "type": metadata.get("document_type", [None])[0] if metadata.get("document_type") else None,
        "authorships": authorships,
        "primary_location": {},
        "primary_topic": None,
        "topics": [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search_authors(name: str) -> list[dict]:
    """
    Search the INSPIRE /authors endpoint for *name*.

    Returns a list of author candidates (each with ``id`` as the INSPIRE
    control_number and ``name`` in "First Last" form for use with
    ``_names_match``).  Returns an empty list when nothing is found.
    """
    cache_key = f"inspire_search:{name.lower()}"
    hit, cached = await _author_search_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0) as client:
        response = await _get_with_retry(
            client,
            f"{_BASE_URL}/authors",
            {"q": name, "fields": "name,ids,affiliations,stats", "size": 5},
            context=f"inspire-author-search:{name}",
        )

    if response is None or response.status_code != 200:
        await _author_search_cache.set(cache_key, [])
        return []

    try:
        hits = response.json().get("hits", {}).get("hits", [])
    except (ValueError, AttributeError):
        hits = []

    candidates: list[dict] = []
    for hit_item in hits:
        meta = hit_item.get("metadata", {})
        raw_name = meta.get("name", {}).get("value", "")
        display_name = _inspire_to_first_last(raw_name) if raw_name else ""
        if not display_name:
            continue
        paper_count = (meta.get("stats") or {}).get("number_of_papers", 0)
        # Use the raw "Last, First" name as the authorId — this is the form
        # that INSPIRE's literature `a` query accepts directly.
        candidates.append({
            "name": display_name,
            "authorId": raw_name,
            "paperCount": paper_count,
        })

    await _author_search_cache.set(cache_key, candidates)
    return candidates


async def get_works_by_author(author_id: str) -> list[dict]:
    """
    Fetch INSPIRE literature records for *author_id* (INSPIRE control_number).

    Paginates through results and returns normalized OA-compatible work dicts.
    Only records that yield a DOI or arXiv identifier are included.
    """
    cache_key = f"inspire_works:{author_id}"
    hit, cached = await _works_by_author_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    works: list[dict] = []
    page = 1

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while len(works) < _MAX_RESULTS:
            response = await _get_with_retry(
                client,
                f"{_BASE_URL}/literature",
                {
                    "q": f"a {author_id}",
                    "fields": "titles,dois,arxiv_eprints,authors,earliest_date,imprint,document_type",
                    "sort": "mostrecent",
                    "size": _PAGE_SIZE,
                    "page": page,
                },
                context=f"inspire-works:{author_id}:page{page}",
            )

            if response is None or response.status_code != 200:
                if response is not None:
                    logger.warning(
                        "INSPIRE literature returned %s for author %r (page %d)",
                        response.status_code, author_id, page,
                    )
                break

            try:
                body = response.json()
                hits = body.get("hits", {})
                records = hits.get("hits", [])
                total = int(hits.get("total", 0))
            except (ValueError, AttributeError):
                break

            for record in records:
                work = _normalize_work(record)
                if work:
                    works.append(work)

            fetched_so_far = (page - 1) * _PAGE_SIZE + len(records)
            if not records or fetched_so_far >= total:
                break
            page += 1

    logger.info(
        "INSPIRE-HEP: normalized %d works for author %r", len(works), author_id
    )
    await _works_by_author_cache.set(cache_key, works)
    return works

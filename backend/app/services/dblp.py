"""
DBLP Computer Science Bibliography API client.

Used as a cross-source coverage boost for CS conference and journal papers.
DBLP indexes virtually every ACM, IEEE, and major CS conference paper —
many of which are absent from OpenAlex and Semantic Scholar or lack DOIs
in those sources.

No API key required.

Docs: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
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

_BASE_URL = "https://dblp.org/search"
_HEADERS = {
    "User-Agent": "Citey/0.1 (mailto:support@citey.app)",
    "Accept": "application/json",
}
_PAGE_SIZE = 250   # DBLP allows up to 1000; 250 is safe and fast
_MAX_RESULTS = 1000
_MAX_RETRIES = 4

# DBLP profile URL prefix used to extract the PID.
_PID_PREFIX = "https://dblp.org/pid/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_pid(profile_url: str) -> str:
    """
    Extract the DBLP author PID from a profile URL.

    ``https://dblp.org/pid/12/3456`` → ``12/3456``
    ``https://dblp.org/pid/d/TimothyDo`` → ``d/TimothyDo``
    Returns the raw URL string if the prefix is missing.
    """
    if profile_url.startswith(_PID_PREFIX):
        return profile_url[len(_PID_PREFIX):]
    return profile_url


def _coerce_authors(raw: Any) -> list[dict]:
    """
    DBLP returns ``authors.author`` as a list when there are multiple
    authors, but as a plain dict when there is only one.  Normalise to list.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []


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
            logger.error("DBLP request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "DBLP rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error("DBLP rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context)
    return None


def _normalize_work(hit: dict) -> dict | None:
    """
    Convert a single DBLP publication search hit to an OA-compatible dict.
    Returns ``None`` if the record has no DOI.
    """
    info = hit.get("info", {})

    doi_raw = (info.get("doi") or "").strip()
    if not doi_raw:
        return None

    doi = doi_raw if doi_raw.startswith("http") else f"https://doi.org/{doi_raw}"

    title = (info.get("title") or "").strip().rstrip(".")
    year_str = str(info.get("year") or "")
    try:
        year = int(year_str) if year_str.isdigit() else None
    except ValueError:
        year = None

    # Authors: DBLP nests them under info.authors.author (list or dict)
    raw_authors = _coerce_authors((info.get("authors") or {}).get("author", []))
    authorships = []
    for author_entry in raw_authors:
        name = ""
        if isinstance(author_entry, dict):
            name = (author_entry.get("text") or "").strip()
        elif isinstance(author_entry, str):
            name = author_entry.strip()
        if name:
            authorships.append({"author": {"id": "", "display_name": name}})

    dblp_key = info.get("key") or hit.get("@id") or ""

    return {
        "doi": doi,
        "title": title,
        "publication_year": year,
        "id": f"dblp:{dblp_key}",
        "cited_by_count": 0,
        "type": info.get("type"),
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
    Search the DBLP author index for *name*.

    Returns a list of candidates, each with:
    - ``name``:     display name as stored by DBLP
    - ``authorId``: DBLP PID (e.g. ``12/3456``) used in publication queries
    """
    cache_key = f"dblp_search:{name.lower()}"
    hit, cached = await _author_search_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0) as client:
        response = await _get_with_retry(
            client,
            f"{_BASE_URL}/author/api",
            {"q": name, "format": "json", "h": 5},
            context=f"dblp-author-search:{name}",
        )

    if response is None or response.status_code != 200:
        await _author_search_cache.set(cache_key, [])
        return []

    try:
        hits_raw = (
            response.json()
            .get("result", {})
            .get("hits", {})
            .get("hit", [])
        )
    except (ValueError, AttributeError):
        hits_raw = []

    # DBLP returns a single dict (not a list) when exactly one result matches
    if isinstance(hits_raw, dict):
        hits_raw = [hits_raw]

    candidates: list[dict] = []
    for h in hits_raw:
        info = h.get("info", {})
        display_name = (info.get("author") or "").strip()
        profile_url = (info.get("url") or "").strip()
        if not display_name or not profile_url:
            continue
        pid = _extract_pid(profile_url)
        candidates.append({"name": display_name, "authorId": pid})

    await _author_search_cache.set(cache_key, candidates)
    return candidates


async def get_works_by_author(author_pid: str) -> list[dict]:
    """
    Fetch all DBLP publications for the author identified by *author_pid*.

    Uses the publication search endpoint with ``author:{pid}`` to scope
    results precisely to one person, then paginates in batches.
    Only publications that carry a DOI are returned.
    """
    cache_key = f"dblp_works:{author_pid}"
    hit, cached = await _works_by_author_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    works: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while offset < _MAX_RESULTS:
            response = await _get_with_retry(
                client,
                f"{_BASE_URL}/publ/api",
                {
                    "q": f"author:{author_pid}",
                    "format": "json",
                    "h": _PAGE_SIZE,
                    "f": offset,
                },
                context=f"dblp-works:{author_pid}:f{offset}",
            )

            if response is None or response.status_code != 200:
                if response is not None:
                    logger.warning(
                        "DBLP publication search returned %s for pid %r (f=%d)",
                        response.status_code, author_pid, offset,
                    )
                break

            try:
                result = response.json().get("result", {})
                hits_info = result.get("hits", {})
                total = int(hits_info.get("@total", 0))
                hits_raw = hits_info.get("hit", [])
            except (ValueError, AttributeError):
                break

            # Single result returned as dict, not list
            if isinstance(hits_raw, dict):
                hits_raw = [hits_raw]

            for pub_hit in hits_raw:
                work = _normalize_work(pub_hit)
                if work:
                    works.append(work)

            offset += len(hits_raw)
            if not hits_raw or offset >= total:
                break

    logger.info(
        "DBLP: normalized %d works with DOIs for pid %r", len(works), author_pid
    )
    await _works_by_author_cache.set(cache_key, works)
    return works

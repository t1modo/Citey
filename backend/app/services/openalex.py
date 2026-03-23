"""
OpenAlex REST API client.

Docs: https://docs.openalex.org/
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org"
_HEADERS = {
    "User-Agent": "Citey/0.1 (mailto:support@citey.app)",
}
_PER_PAGE = 200  # Maximum allowed by the API
_MAILTO = "support@citey.app"
_MAX_RETRIES = 4


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url* with automatic retry on HTTP 429 (rate-limit) responses.

    Waits for the duration given in the ``Retry-After`` header, falling back
    to exponential back-off (2^attempt seconds) when the header is absent.
    Returns ``None`` on network errors or when all retries are exhausted.
    All other status codes are returned immediately so the caller can decide.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("OpenAlex request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "OpenAlex rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error("OpenAlex rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context)
    return None


async def get_work_by_doi(doi: str) -> dict | None:
    """
    Look up an OpenAlex work by DOI.
    Returns the raw work dict, or None if not found.

    Uses the filter endpoint rather than a path-based lookup so that DOIs with
    multiple slashes (e.g. ACL Anthology 10.18653/v1/...) are not mis-parsed as
    extra URL path segments by OpenAlex's router.
    """
    clean_doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if clean_doi.lower().startswith(prefix):
            clean_doi = clean_doi[len(prefix):]
            break

    url = f"{_BASE_URL}/works"
    params = {
        "filter": f"doi:https://doi.org/{clean_doi}",
        "per_page": 1,
        "mailto": _MAILTO,
    }
    logger.debug("OpenAlex work lookup by DOI filter: %s", clean_doi)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("OpenAlex request error for DOI %s: %s", doi, exc)
            return None

    if response.status_code == 404:
        logger.debug("OpenAlex: work not found for DOI %s", doi)
        return None

    if response.status_code != 200:
        logger.warning(
            "OpenAlex unexpected status %s for DOI %s", response.status_code, doi
        )
        return None

    results = response.json().get("results", [])
    return results[0] if results else None


async def get_citing_works(
    openalex_work_id: str,
    since_date: str | None = None,
) -> list[dict]:
    """
    Retrieve all works that cite *openalex_work_id* via cursor-based pagination.

    Parameters
    ----------
    openalex_work_id:
        The short OpenAlex ID, e.g. ``W2741809807`` or the full URL form
        ``https://openalex.org/W2741809807``.  Both are accepted.
    since_date:
        Optional ISO date string (``YYYY-MM-DD``).  When provided, only citing
        works published on or after this date are returned.

    Returns a flat list of raw OpenAlex work dicts.
    """
    # Normalise to the short form so it can be used in filter strings.
    work_id = openalex_work_id
    if work_id.startswith("https://openalex.org/"):
        work_id = work_id[len("https://openalex.org/"):]

    filters = [f"cites:{work_id}"]
    if since_date:
        filters.append(f"from_publication_date:{since_date}")
    filter_str = ",".join(filters)

    results: list[dict] = []
    cursor = "*"

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while True:
            params: dict[str, Any] = {
                "filter": filter_str,
                "per_page": _PER_PAGE,
                "cursor": cursor,
                "mailto": _MAILTO,
            }
            logger.debug(
                "OpenAlex citing works page, cursor=%s, filter=%s", cursor, filter_str
            )
            response = await _get_with_retry(
                client, f"{_BASE_URL}/works", params, context=f"citing:{openalex_work_id}"
            )
            if response is None:
                break
            if response.status_code != 200:
                logger.warning(
                    "OpenAlex unexpected status %s for citing works of %s",
                    response.status_code,
                    openalex_work_id,
                )
                break

            payload = response.json()
            page_results: list[dict] = payload.get("results", [])
            results.extend(page_results)

            meta: dict = payload.get("meta", {})
            next_cursor = meta.get("next_cursor")

            # next_cursor being absent/null is the authoritative end-of-pagination
            # signal from OpenAlex.  A partial page is NOT a reliable stop condition
            # because the API can return fewer than _PER_PAGE results mid-stream
            # (e.g. after server-side filtering) while still having more pages.
            if not next_cursor:
                break

            cursor = next_cursor

    logger.info(
        "OpenAlex: found %d citing works for %s", len(results), openalex_work_id
    )
    return results


async def get_citation_counts(openalex_ids: list[str]) -> dict[str, int]:
    """
    Fetch cited_by_count for a list of OpenAlex work IDs in batches.

    Returns a dict mapping short OpenAlex ID (e.g. "W2741809807") to count.
    Uses the filter endpoint so we can batch up to 200 IDs per request.
    """
    if not openalex_ids:
        return {}

    def _short(oid: str) -> str:
        return oid[len("https://openalex.org/"):] if oid.startswith("https://openalex.org/") else oid

    short_ids = [_short(oid) for oid in openalex_ids]
    counts: dict[str, int] = {}

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        # OpenAlex supports up to 200 per_page; batch 200 IDs at a time.
        batch_size = 200
        for i in range(0, len(short_ids), batch_size):
            batch = short_ids[i : i + batch_size]
            filter_str = "ids.openalex:" + "|".join(batch)
            params: dict[str, Any] = {
                "filter": filter_str,
                "select": "id,cited_by_count",
                "per_page": batch_size,
                "mailto": _MAILTO,
            }
            response = await _get_with_retry(
                client, f"{_BASE_URL}/works", params, context="citation_counts_batch"
            )
            if response is None:
                continue
            if response.status_code != 200:
                logger.warning(
                    "OpenAlex batch citation count status %s", response.status_code
                )
                continue

            for item in response.json().get("results", []):
                oid = _short(item.get("id", ""))
                cbc = item.get("cited_by_count")
                if oid and cbc is not None:
                    counts[oid] = cbc

    logger.info("OpenAlex: fetched cited_by_count for %d/%d works", len(counts), len(short_ids))
    return counts


async def search_authors(query: str) -> list[dict]:
    """Search OpenAlex for authors by name. Returns up to 5 candidates."""
    url = f"{_BASE_URL}/authors"
    params = {"search": query, "per_page": 5, "mailto": _MAILTO}
    logger.debug("OpenAlex author search: %s", query)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("OpenAlex author search error for query %s: %s", query, exc)
            return []

    if response.status_code != 200:
        logger.warning("OpenAlex author search status %s for query %s", response.status_code, query)
        return []

    return response.json().get("results", [])


async def get_works_by_author(author_id: str) -> list[dict]:
    """
    Fetch all works for an OpenAlex author ID via cursor-based pagination.
    author_id may be the short form (A12345) or the full URL form.
    """
    if author_id.startswith("https://openalex.org/"):
        author_id = author_id[len("https://openalex.org/"):]

    results: list[dict] = []
    cursor = "*"

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while True:
            params: dict[str, Any] = {
                "filter": f"author.id:{author_id}",
                "per_page": _PER_PAGE,
                "cursor": cursor,
                "mailto": _MAILTO,
            }
            response = await _get_with_retry(
                client, f"{_BASE_URL}/works", params, context=f"author:{author_id}"
            )
            if response is None:
                break
            if response.status_code != 200:
                logger.warning(
                    "OpenAlex status %s fetching works for author %s",
                    response.status_code,
                    author_id,
                )
                break

            payload = response.json()
            page_results: list[dict] = payload.get("results", [])
            results.extend(page_results)

            meta = payload.get("meta", {})
            next_cursor = meta.get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor

    logger.info("OpenAlex: found %d works for author %s", len(results), author_id)
    return results


def extract_topics(raw: dict) -> list[str]:
    """
    Extract up to 3 subject topic display names from a raw OpenAlex work dict.
    Uses ``primary_topic`` first (highest-scoring), then the ``topics`` array.
    """
    seen: set[str] = set()
    topics: list[str] = []
    primary = ((raw.get("primary_topic") or {}).get("display_name") or "").strip()
    if primary:
        topics.append(primary)
        seen.add(primary)
    for t in raw.get("topics", []):
        name = (t.get("display_name") or "").strip()
        if name and name not in seen:
            topics.append(name)
            seen.add(name)
        if len(topics) >= 3:
            break
    return topics


def extract_venue(raw: dict) -> str | None:
    """
    Extract the primary publication venue name (journal, conference, repository)
    from a raw OpenAlex work dict.
    """
    loc = raw.get("primary_location") or {}
    source = loc.get("source") or {}
    name = (source.get("display_name") or "").strip()
    return name or None


def normalize_citing_work(raw: dict) -> dict[str, Any]:
    """
    Convert a raw OpenAlex work dict into the normalised shape used throughout
    the application.

    Returned keys:
        id, doi, title, authors, affiliations, year, url
    """
    openalex_id: str = raw.get("id", "")
    doi: str | None = raw.get("doi")  # Full URL form, e.g. "https://doi.org/10..."
    if doi:
        # Normalise to bare DOI string.
        for prefix in ("https://doi.org/", "http://doi.org/"):
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
                break
        doi = doi.lower()

    title: str = raw.get("title") or "Untitled"

    # --- Authors and affiliations ------------------------------------------------
    authors: list[str] = []
    affiliations: list[str] = []
    seen_affiliations: set[str] = set()

    for authorship in raw.get("authorships", []):
        author_info = authorship.get("author", {})
        display_name: str = author_info.get("display_name", "").strip()
        if display_name:
            authors.append(display_name)

        for inst in authorship.get("institutions", []):
            inst_name: str = inst.get("display_name", "").strip()
            if inst_name and inst_name not in seen_affiliations:
                affiliations.append(inst_name)
                seen_affiliations.add(inst_name)

    # --- Publication year and date -----------------------------------------------
    year: int | None = raw.get("publication_year")
    publication_date: str | None = raw.get("publication_date")  # e.g. "2026-02-27"

    # --- Canonical URL -----------------------------------------------------------
    if doi:
        url = f"https://doi.org/{doi}"
    else:
        url = raw.get("landing_page_url") or None

    return {
        "id": openalex_id,
        "doi": doi,
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "year": year,
        "publication_date": publication_date,
        "url": url,
    }

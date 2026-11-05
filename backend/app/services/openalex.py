"""
OpenAlex REST API client.

Docs: https://docs.openalex.org/
"""

import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.services.cache import AsyncTTLCache
from app.services.source_errors import SourceUnavailable

logger = logging.getLogger(__name__)

# Cache author search results for 5 minutes — same query is often repeated
# during the import flow as users refine their input.
_author_search_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=300)

# Cache full works lists for 1 hour — cursor-paginated and expensive; called
# by both the import flow and the weekly publication-sync job.
_works_by_author_cache: AsyncTTLCache = AsyncTTLCache(maxsize=100, ttl=3600)

_BASE_URL = "https://api.openalex.org"
_HEADERS = {
    "User-Agent": "Citey/0.1 (mailto:support@citey.email)",
}
_PER_PAGE = 200  # Maximum allowed by the API
_MAILTO = "support@citey.email"
_MAX_RETRIES = 4
_JUNK_FILTER = "is_paratext:false,is_retracted:false,type:!erratum,type:!retraction,type:!paratext"
# Indirection so tests can skip real waiting.
_sleep = asyncio.sleep


def _oa_client(timeout: float) -> httpx.AsyncClient:
    """An httpx client for OpenAlex that sends the API key, when one is set,
    as the ``api_key`` query parameter on every request."""
    from app.config import get_settings

    key = get_settings().openalex_api_key
    return httpx.AsyncClient(
        headers=_HEADERS, timeout=timeout, params={"api_key": key} if key else None
    )


def _retry_after(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying, from Retry-After or exponential backoff.

    Retry-After may be seconds or an HTTP date; ``int()`` on a date used to
    raise and throw away everything fetched so far.
    """
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                when = parsedate_to_datetime(header)
                return max(0.0, (when - datetime.now(tz=timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return float(2 ** attempt)


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url*, retrying rate limits (429), server errors (5xx) and network
    errors with backoff.

    Returns the response for any other status (the caller decides), the last
    5xx response if the server never recovers, or ``None`` when every attempt
    was rate limited or failed at the network level.
    """
    response: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.warning("OpenAlex request error [%s] (attempt %d/%d): %s",
                           context, attempt + 1, _MAX_RETRIES, exc)
            response = None
            await _sleep(float(2 ** attempt))
            continue
        if response.status_code == 429:
            wait = _retry_after(response, attempt)
            logger.warning(
                "OpenAlex rate limited (429) [%s]; waiting %.0fs (attempt %d/%d)",
                context, wait, attempt + 1, _MAX_RETRIES,
            )
            response = None
            await _sleep(wait)
            continue
        if response.status_code >= 500:
            logger.warning("OpenAlex server error %s [%s] (attempt %d/%d)",
                           response.status_code, context, attempt + 1, _MAX_RETRIES)
            await _sleep(float(2 ** attempt))
            continue
        return response
    logger.error("OpenAlex did not recover after %d attempts [%s]", _MAX_RETRIES, context)
    return response


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

    async with _oa_client(timeout=15.0) as client:
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
    base_filter = ",".join(filters)
    # Journal front matter, errata, retraction notices and retracted papers
    # are not citations worth an alert.
    filter_str = base_filter + "," + _JUNK_FILTER

    results: list[dict] = []
    cursor = "*"

    async with _oa_client(timeout=30.0) as client:
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
            if (
                response is not None
                and response.status_code == 400
                and filter_str != base_filter
                and cursor == "*"
            ):
                # Never let the optional junk filter block citation checks.
                logger.warning(
                    "OpenAlex rejected the junk filter for %s; retrying without it", openalex_work_id
                )
                filter_str = base_filter
                continue
            # A failed page must not look like "no more citations": the caller
            # would record the work as checked and the missing citations
            # would never be looked for again.
            if response is None or response.status_code != 200:
                status = response.status_code if response is not None else "no response"
                logger.warning(
                    "OpenAlex citing works fetch failed (%s) for %s after %d result(s)",
                    status, openalex_work_id, len(results),
                )
                raise SourceUnavailable("openalex", f"citing works for {openalex_work_id}: {status}")

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


def _is_work_id(value: str) -> bool:
    from app.models import is_openalex_work_id
    return is_openalex_work_id(value)


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

    # One foreign ID ("S2:…") makes OpenAlex reject the whole batch, which
    # used to leave every count for that user stale.
    short_ids = [_short(oid) for oid in openalex_ids if _is_work_id(oid)]
    counts: dict[str, int] = {}

    async with _oa_client(timeout=30.0) as client:
        # OpenAlex allows at most 100 values in one OR filter; stay under it.
        batch_size = 50
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


async def get_authors_by_ids(author_ids: list[str]) -> list[dict]:
    """Batch-fetch full OpenAlex author records by their IDs.

    Returns a list in arbitrary order; caller should key by 'id' if ordering matters.
    Silently returns an empty list on any error.
    """
    if not author_ids:
        return []

    short_ids = [
        aid[len("https://openalex.org/"):] if aid.startswith("https://openalex.org/") else aid
        for aid in author_ids[:25]
    ]
    url = f"{_BASE_URL}/authors"
    params: dict[str, Any] = {
        "filter": f"ids.openalex:{'|'.join(short_ids)}",
        "per_page": len(short_ids),
        "mailto": _MAILTO,
    }
    logger.debug("OpenAlex batch author lookup: %d ids", len(short_ids))

    async with _oa_client(timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("OpenAlex batch author lookup error: %s", exc)
            return []

    if response.status_code != 200:
        logger.warning("OpenAlex batch author lookup status %s", response.status_code)
        return []

    return response.json().get("results", [])


async def search_authors(query: str) -> list[dict]:
    """Search OpenAlex for authors by name. Returns up to 10 candidates."""
    hit, cached = await _author_search_cache.get(query)
    if hit:
        logger.debug("OpenAlex author search cache hit: %s", query)
        return cached

    url = f"{_BASE_URL}/authors"
    params: dict[str, Any] = {"search": query, "per_page": 10, "mailto": _MAILTO}
    logger.debug("OpenAlex author search: %s", query)

    async with _oa_client(timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("OpenAlex author search error for query %s: %s", query, exc)
            return []

    if response.status_code != 200:
        logger.warning("OpenAlex author search status %s for query %s", response.status_code, query)
        return []

    results = response.json().get("results", [])
    await _author_search_cache.set(query, results)
    return results


async def get_works_by_author(author_id: str) -> list[dict]:
    """
    Fetch all works for an OpenAlex author ID via cursor-based pagination.
    author_id may be the short form (A12345) or the full URL form.
    """
    if author_id.startswith("https://openalex.org/"):
        author_id = author_id[len("https://openalex.org/"):]

    hit, cached = await _works_by_author_cache.get(author_id)
    if hit:
        logger.debug("OpenAlex works-by-author cache hit: %s", author_id)
        return cached

    results: list[dict] = []
    cursor = "*"

    async with _oa_client(timeout=30.0) as client:
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
    await _works_by_author_cache.set(author_id, results)
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


def _jacow_venue(doi: str) -> str | None:
    """Extract human-readable conference name from a JACoW DOI.

    JACoW DOIs follow the pattern 10.18429/jacow-{confcode}{year}-{paperid}.
    Example: 10.18429/jacow-napac2025-tup099 → "NAPAC 2025"
    """
    import re
    lower = doi.lower()
    prefix = "10.18429/jacow-"
    if not lower.startswith(prefix):
        return None
    rest = lower[len(prefix):]           # e.g. "napac2025-tup099"
    slug = rest.split("-")[0]            # e.g. "napac2025"
    m = re.match(r"^([a-z]+)(\d{4})$", slug)
    if not m:
        return None
    conf, year = m.group(1).upper(), m.group(2)
    return f"{conf} {year}"


def extract_venue(raw: dict) -> str | None:
    """
    Extract the primary publication venue name (journal, conference, repository)
    from a raw OpenAlex work dict.
    """
    # For JACoW conference proceedings the DOI encodes the conference name
    # precisely; OpenAlex sometimes assigns an unrelated source name (e.g.
    # "Open MIND") to these papers.  Always prefer the DOI-derived name.
    doi_raw = raw.get("doi") or ""
    for pfx in ("https://doi.org/", "http://doi.org/"):
        if doi_raw.startswith(pfx):
            doi_raw = doi_raw[len(pfx):]
            break
    jacow = _jacow_venue(doi_raw)
    if jacow:
        return jacow

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

    # arXiv id from any location that is an arXiv page, so the preprint and
    # the journal version are recognised as one paper.
    from app.services.citing_identity import arxiv_id_from_doi, arxiv_id_from_url

    arxiv_id = arxiv_id_from_doi(doi)
    for loc in raw.get("locations") or []:
        if arxiv_id:
            break
        arxiv_id = arxiv_id_from_url((loc or {}).get("landing_page_url"))

    return {
        "id": openalex_id,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "type": raw.get("type"),
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "year": year,
        "publication_date": publication_date,
        "url": url,
    }

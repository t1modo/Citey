"""
NASA Astrophysics Data System (ADS) API client.

Used as a cross-source coverage boost for astrophysics, space science, and
related physical-sciences literature — a major gap in OpenAlex and S2.

Requires a free personal API token:
  https://ui.adsabs.harvard.edu/user/settings/token

Set ``ADS_API_KEY`` in your ``.env`` file.  If the key is absent the service
returns empty results gracefully so the rest of the import is unaffected.

Docs: https://ui.adsabs.harvard.edu/help/api/
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.services.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

_author_search_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=300)
_works_by_author_cache: AsyncTTLCache = AsyncTTLCache(maxsize=100, ttl=3600)

_BASE_URL = "https://api.adsabs.harvard.edu/v1"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.app)"}
_FIELDS = "bibcode,title,year,author,doi,pubdate,doctype"
_MAX_RESULTS = 2000   # ADS allows up to 2000 rows per query
_BATCH_SIZE = 200     # rows per paginated request
_MAX_RETRIES = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_token() -> str:
    """Return the configured ADS API token, or an empty string if absent."""
    from app.config import get_settings
    return get_settings().ads_api_key or ""


def _first_last_to_ads(name: str) -> str:
    """
    Convert a "First [Middle] Last" name to ADS author-query format "Last, First".

    ADS stores author names as "Last, First" — using this format in queries
    significantly reduces false-positive results versus a bare keyword search.
    """
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


def _ads_author_to_first_last(ads_name: str) -> str:
    """
    Convert ADS-style "Last, First" to "First Last" for use with _names_match.
    Leaves already-converted names unchanged.
    """
    if "," in ads_name:
        last, _, first = ads_name.partition(",")
        return f"{first.strip()} {last.strip()}"
    return ads_name


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url* with automatic retry on HTTP 429 responses.
    Returns ``None`` on network errors or exhausted retries.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("ADS request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "ADS rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error("ADS rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context)
    return None


def _normalize_work(doc: dict) -> dict | None:
    """
    Convert an ADS search-result document to an OpenAlex-compatible work dict.
    Returns ``None`` if the document has no usable DOI.
    """
    # ADS returns DOIs as a list; take the first.
    doi_list = doc.get("doi") or []
    doi: str | None = None
    for raw_doi in doi_list:
        raw_doi = raw_doi.strip()
        if raw_doi:
            doi = raw_doi
            break

    if not doi:
        return None

    if not doi.startswith("http"):
        doi = f"https://doi.org/{doi}"

    # Title is a list in ADS; take the first element.
    title_list = doc.get("title") or []
    title = (title_list[0] if title_list else "").strip()

    year_raw = doc.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None

    # Authors: ADS returns "Last, First" strings — convert to "First Last"
    authorships = []
    for ads_name in (doc.get("author") or []):
        display = _ads_author_to_first_last(ads_name.strip())
        if display:
            authorships.append({"author": {"id": "", "display_name": display}})

    bibcode = doc.get("bibcode") or ""

    return {
        "doi": doi,
        "title": title,
        "publication_year": year,
        "id": f"ads:{bibcode}",
        "cited_by_count": 0,
        "type": doc.get("doctype"),
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
    Probe ADS for papers attributed to *name*.  Returns a single pseudo-
    candidate (like PubMed) if results exist, empty list otherwise.

    Skipped silently if ``ADS_API_KEY`` is not configured.
    """
    token = _get_token()
    if not token:
        return []

    cache_key = f"ads_search:{name.lower()}"
    hit, cached = await _author_search_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    ads_name = _first_last_to_ads(name)
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await _get_with_retry(
            client,
            f"{_BASE_URL}/search/query",
            {
                "q": f'author:"{ads_name}"',
                "fl": "bibcode",
                "rows": 1,
            },
            context=f"ads-author-probe:{name}",
        )

    if response is None or response.status_code != 200:
        await _author_search_cache.set(cache_key, [])
        return []

    try:
        num_found = int(response.json().get("response", {}).get("numFound", 0))
    except (ValueError, AttributeError):
        num_found = 0

    result: list[dict] = (
        [{"name": name, "authorId": name, "paperCount": num_found}] if num_found > 0 else []
    )
    await _author_search_cache.set(cache_key, result)
    return result


async def get_works_by_author(author_name: str) -> list[dict]:
    """
    Fetch ADS papers attributed to *author_name* and return them as
    OpenAlex-compatible work dicts (only papers that carry a DOI).

    Paginates through results in batches of ``_BATCH_SIZE`` rows.
    Skipped silently if ``ADS_API_KEY`` is not configured.
    """
    token = _get_token()
    if not token:
        return []

    cache_key = f"ads_works:{author_name.lower()}"
    hit, cached = await _works_by_author_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    ads_name = _first_last_to_ads(author_name)
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    works: list[dict] = []

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        start = 0
        while start < _MAX_RESULTS:
            response = await _get_with_retry(
                client,
                f"{_BASE_URL}/search/query",
                {
                    "q": f'author:"{ads_name}"',
                    "fl": _FIELDS,
                    "rows": _BATCH_SIZE,
                    "start": start,
                    "sort": "date desc",
                },
                context=f"ads-works:{author_name}:start{start}",
            )

            if response is None or response.status_code != 200:
                if response is not None:
                    logger.warning(
                        "ADS works query returned %s for author %r (start=%d)",
                        response.status_code, author_name, start,
                    )
                break

            try:
                body = response.json()
                resp = body.get("response", {})
                docs = resp.get("docs", [])
                num_found = int(resp.get("numFound", 0))
            except (ValueError, AttributeError):
                break

            for doc in docs:
                work = _normalize_work(doc)
                if work:
                    works.append(work)

            start += len(docs)
            if not docs or start >= num_found:
                break

    logger.info(
        "ADS: normalized %d works with DOIs for author %r", len(works), author_name
    )
    await _works_by_author_cache.set(cache_key, works)
    return works

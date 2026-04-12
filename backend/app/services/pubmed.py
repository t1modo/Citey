"""
PubMed (NCBI E-utilities) API client.

Used as a cross-source coverage boost for biomedical and life-science works.
PubMed is paper-centric (no author-profile endpoint), so we search by author
name directly and paginate through the results.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.services.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

# Cache author probes for 5 minutes (same as OA / S2 author-search caches).
_author_search_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=300)

# Cache full works lists for 1 hour.
_works_by_author_cache: AsyncTTLCache = AsyncTTLCache(maxsize=100, ttl=3600)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.app)"}
_TOOL = "citey"
_EMAIL = "support@citey.app"
_MAX_RESULTS = 1000   # Maximum PMIDs fetched in one esearch call
_BATCH_SIZE = 200     # PMIDs per esummary request (NCBI recommended max)
_MAX_RETRIES = 4


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url* with automatic retry on HTTP 429 (rate-limit) responses.

    Returns ``None`` on network errors or when all retries are exhausted.
    All other status codes are returned immediately so the caller can decide.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("PubMed request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "PubMed rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error("PubMed rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context)
    return None


def _normalize_work(summary: dict, pmid: str) -> dict | None:
    """
    Convert a PubMed esummary record to an OpenAlex-compatible work dict.
    Returns ``None`` if the record has no DOI (we require DOIs for dedup).
    """
    doi: str | None = None
    for id_entry in summary.get("articleids", []):
        if id_entry.get("idtype") == "doi":
            raw = id_entry.get("value", "").strip()
            if raw:
                doi = raw
                break

    if not doi:
        return None

    # Ensure the DOI is stored in full-URL form to match OA / S2 normalisation.
    if not doi.startswith("http"):
        doi = f"https://doi.org/{doi}"

    title = summary.get("title", "").strip().rstrip(".")
    year_str = (summary.get("pubdate") or "")[:4]
    try:
        year = int(year_str) if year_str.isdigit() else None
    except ValueError:
        year = None

    authorships = []
    for author in summary.get("authors", []):
        name = author.get("name", "").strip()
        if name:
            authorships.append({"author": {"id": "", "display_name": name}})

    return {
        "doi": doi,
        "title": title,
        "publication_year": year,
        "id": f"pubmed:{pmid}",
        "cited_by_count": 0,
        "type": "article",
        "authorships": authorships,
        "primary_location": {},
        "primary_topic": None,
        "topics": [],
    }


async def search_authors(name: str) -> list[dict]:
    """
    PubMed doesn't have author-profile endpoints, so this performs a quick
    esearch probe to confirm the author appears in PubMed at all.  Returns a
    single pseudo-candidate whose ``authorId`` is the author name (used
    verbatim as the search term in :func:`get_works_by_author`), or an empty
    list if no PubMed results exist.
    """
    cache_key = f"pm_search:{name.lower()}"
    hit, cached = await _author_search_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0) as client:
        response = await _get_with_retry(
            client,
            f"{_BASE_URL}/esearch.fcgi",
            {
                "db": "pubmed",
                "term": f"{name}[Author]",
                "retmax": 1,
                "retmode": "json",
                "tool": _TOOL,
                "email": _EMAIL,
            },
            context=f"pm-author-probe:{name}",
        )

    if response is None or response.status_code != 200:
        await _author_search_cache.set(cache_key, [])
        return []

    try:
        count = int(response.json().get("esearchresult", {}).get("count", 0))
    except (ValueError, AttributeError):
        count = 0

    result: list[dict] = (
        [{"name": name, "authorId": name, "paperCount": count}] if count > 0 else []
    )
    await _author_search_cache.set(cache_key, result)
    return result


async def get_works_by_author(author_name: str) -> list[dict]:
    """
    Fetch PubMed papers attributed to *author_name* and return them as
    OpenAlex-compatible work dicts (only papers that have a DOI are included).

    Two-step NCBI workflow:
      1. ``esearch`` — retrieve up to ``_MAX_RESULTS`` PMIDs.
      2. ``esummary`` — fetch metadata in batches of ``_BATCH_SIZE``.
    """
    cache_key = f"pm_works:{author_name.lower()}"
    hit, cached = await _works_by_author_cache.get(cache_key)
    if hit:
        return cached  # type: ignore[return-value]

    # Step 1: get PMIDs
    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        response = await _get_with_retry(
            client,
            f"{_BASE_URL}/esearch.fcgi",
            {
                "db": "pubmed",
                "term": f"{author_name}[Author]",
                "retmax": _MAX_RESULTS,
                "retmode": "json",
                "tool": _TOOL,
                "email": _EMAIL,
            },
            context=f"pm-esearch:{author_name}",
        )

    if response is None or response.status_code != 200:
        return []

    try:
        pmids: list[str] = response.json().get("esearchresult", {}).get("idlist", [])
    except (ValueError, AttributeError):
        pmids = []

    if not pmids:
        logger.info("PubMed: no results for author %r", author_name)
        await _works_by_author_cache.set(cache_key, [])
        return []

    logger.info("PubMed: found %d PMIDs for author %r", len(pmids), author_name)

    # Step 2: fetch summaries in batches
    works: list[dict] = []
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        for i in range(0, len(pmids), _BATCH_SIZE):
            batch = pmids[i : i + _BATCH_SIZE]
            summary_response = await _get_with_retry(
                client,
                f"{_BASE_URL}/esummary.fcgi",
                {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "json",
                    "tool": _TOOL,
                    "email": _EMAIL,
                },
                context=f"pm-esummary:{author_name}:batch{i}",
            )
            if summary_response is None or summary_response.status_code != 200:
                logger.warning(
                    "PubMed: esummary batch %d failed for author %r", i, author_name
                )
                continue

            try:
                result_data = summary_response.json().get("result", {})
            except (ValueError, AttributeError):
                continue

            for pmid in batch:
                summary = result_data.get(pmid)
                if not summary:
                    continue
                work = _normalize_work(summary, pmid)
                if work:
                    works.append(work)

    logger.info(
        "PubMed: normalized %d works with DOIs for author %r", len(works), author_name
    )
    await _works_by_author_cache.set(cache_key, works)
    return works

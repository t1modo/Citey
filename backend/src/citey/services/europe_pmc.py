"""
Europe PMC client for citing papers.

Docs: https://europepmc.org/RestfulWebService

Europe PMC links citations between PubMed, PubMed Central and life science
preprints from full text and reference lists, which catches biomedical
citations the general indexes miss. Papers outside the life sciences are not
in Europe PMC, and the DOI lookup simply finds nothing for them.
"""

import logging
import re
from typing import Any

import httpx

from citey.services import http_retry
from citey.services.source_errors import SourceUnavailable

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.email)"}
_PAGE_SIZE = 1000  # maximum the search endpoint allows
_MAX_PAGES = 10
# Europe PMC records of the same paper (journal article and its preprint)
# are separate; citations to each are collected.
_MAX_RECORDS = 3
_EMAIL = re.compile(r"\S+@\S+")


def _clean_doi(doi: str) -> str:
    clean = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    return clean.lower()


async def _search(client: httpx.AsyncClient, params: dict[str, Any], context: str) -> dict:
    response = await http_retry.get_with_retry(
        client, _SEARCH_URL, {"format": "json", **params},
        source="Europe PMC", context=context,
    )
    if response is None or response.status_code != 200:
        status = response.status_code if response is not None else "no response"
        raise SourceUnavailable("europe_pmc", f"{context}: {status}")
    try:
        return response.json()
    except ValueError as exc:
        raise SourceUnavailable("europe_pmc", f"{context}: bad JSON") from exc


async def get_citing_works(doi: str, since_date: str | None = None) -> list[dict]:
    """
    Raw Europe PMC records (``resultType=core``) of papers citing *doi*,
    first published on or after *since_date*.

    Returns ``[]`` when the paper is not in Europe PMC. Raises
    :class:`SourceUnavailable` when Europe PMC cannot answer.
    """
    clean = _clean_doi(doi)
    async with httpx.AsyncClient(headers=_HEADERS, timeout=60.0) as client:
        found = await _search(
            client,
            {"query": f'DOI:"{clean}"', "resultType": "lite", "pageSize": 25},
            context=f"lookup {clean}",
        )
        hits = [
            r for r in (found.get("resultList") or {}).get("result", [])
            if (r.get("doi") or "").lower() == clean and r.get("id") and r.get("source")
        ][:_MAX_RECORDS]
        if not hits:
            logger.info("Europe PMC: %s is not indexed", clean)
            return []

        query = " OR ".join(f"CITES:{h['id']}_{h['source']}" for h in hits)
        if len(hits) > 1:
            query = f"({query})"
        if since_date:
            query += f" AND FIRST_PDATE:[{since_date} TO 3000-12-31]"

        results: list[dict] = []
        cursor = "*"
        for _ in range(_MAX_PAGES):
            page = await _search(
                client,
                {"query": query, "resultType": "core", "pageSize": _PAGE_SIZE, "cursorMark": cursor},
                context=f"citing {clean}",
            )
            batch = (page.get("resultList") or {}).get("result", [])
            results.extend(batch)
            next_cursor = page.get("nextCursorMark")
            if not batch or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

    logger.info("Europe PMC: %d citing record(s) for %s", len(results), clean)
    return results


def _work_type(raw: dict) -> str | None:
    types = [t.lower() for t in ((raw.get("pubTypeList") or {}).get("pubType") or [])]
    if any("erratum" in t for t in types):
        return "erratum"
    if any("retraction" in t or "retracted" in t for t in types):
        return "retraction"
    if raw.get("source") == "PPR":
        return "preprint"
    return "article"


def _clean_affiliation(text: str) -> str:
    text = _EMAIL.sub("", text).strip().rstrip(".;, ")
    return re.sub(r"\s{2,}", " ", text)


def normalize_citing_work(raw: dict) -> dict[str, Any]:
    """A raw Europe PMC record in the shape the other normalisers return."""
    from citey.services.citing_identity import arxiv_id_from_doi

    doi = (raw.get("doi") or "").lower() or None
    source, rid = raw.get("source") or "", raw.get("id") or ""

    authors: list[str] = []
    affiliations: list[str] = []
    seen_aff: set[str] = set()
    for author in (raw.get("authorList") or {}).get("author") or []:
        first, last = (author.get("firstName") or "").strip(), (author.get("lastName") or "").strip()
        name = f"{first} {last}".strip() if last else (author.get("fullName") or "").strip()
        if name:
            authors.append(name)
        details = (author.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []
        for aff in details:
            cleaned = _clean_affiliation(aff.get("affiliation") or "")
            if cleaned and cleaned.lower() not in seen_aff:
                seen_aff.add(cleaned.lower())
                affiliations.append(cleaned)
    if not authors and raw.get("authorString"):
        authors = [a.strip() for a in raw["authorString"].rstrip(".").split(",") if a.strip()]

    title = (raw.get("title") or "").strip()
    if title.endswith(".") and not title.endswith(".."):
        title = title[:-1]

    try:
        year = int(raw.get("pubYear")) if raw.get("pubYear") else None
    except (TypeError, ValueError):
        year = None

    if doi:
        url = f"https://doi.org/{doi}"
    elif source and rid:
        url = f"https://europepmc.org/article/{source}/{rid}"
    else:
        url = None

    return {
        "id": f"EPMC:{source}:{rid}" if source and rid else "",
        "doi": doi,
        "arxiv_id": arxiv_id_from_doi(doi),
        "type": _work_type(raw),
        "title": title or "Untitled",
        "authors": authors,
        "affiliations": affiliations,
        "year": year,
        "publication_date": raw.get("firstPublicationDate"),
        "url": url,
    }

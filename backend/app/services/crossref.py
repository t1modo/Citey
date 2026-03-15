"""
DOI resolution with fallback chain: Crossref → OpenAlex → DataCite.

Crossref covers most publisher DOIs.
OpenAlex covers arXiv (10.48550/…) and many other sources.
DataCite covers institutional and non-publisher repositories.
"""

import asyncio
import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.crossref.org/works/"
_DATACITE_URL = "https://api.datacite.org/dois/"
_HEADERS = {
    "User-Agent": "Citey/0.1 (mailto:support@citey.app)",
}


def _extract_authors(message: dict) -> list[str]:
    """Return a list of 'Given Family' strings from the Crossref author array."""
    authors: list[str] = []
    for author in message.get("author", []):
        given = author.get("given", "").strip()
        family = author.get("family", "").strip()
        if given and family:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    return authors


def _extract_year(message: dict) -> int | None:
    """
    Try to pull the publication year from the Crossref message.
    Falls back through issued → published → created date-parts.
    """
    for key in ("issued", "published", "created"):
        date_obj = message.get(key, {})
        parts = date_obj.get("date-parts", [[]])
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                pass
    return None


async def _resolve_from_openalex(doi: str) -> dict[str, Any] | None:
    """Try to resolve a DOI via OpenAlex. Returns None if not found."""
    from app.services.openalex import get_work_by_doi  # avoid circular import at module level

    raw = await get_work_by_doi(doi)
    if raw is None:
        return None

    openalex_doi: str = raw.get("doi", "") or ""
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if openalex_doi.startswith(prefix):
            openalex_doi = openalex_doi[len(prefix):]
            break

    authors: list[str] = []
    for authorship in raw.get("authorships", []):
        name = authorship.get("author", {}).get("display_name", "").strip()
        if name:
            authors.append(name)

    return {
        "doi": openalex_doi or doi,
        "title": raw.get("title") or "Untitled",
        "authors": authors,
        "year": raw.get("publication_year"),
        "url": f"https://doi.org/{openalex_doi or doi}",
        "openalex_id": raw.get("id"),
    }


async def _resolve_from_datacite(doi: str) -> dict[str, Any] | None:
    """Try to resolve a DOI via DataCite. Returns None if not found."""
    url = f"{_DATACITE_URL}{doi}"
    logger.debug("DataCite lookup: %s", url)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.get(url)
        except httpx.RequestError as exc:
            logger.warning("DataCite request error for DOI %s: %s", doi, exc)
            return None

    if response.status_code != 200:
        logger.debug("DataCite: status %s for DOI %s", response.status_code, doi)
        return None

    attrs = response.json().get("data", {}).get("attributes", {})
    titles = attrs.get("titles", [])
    title = titles[0].get("title", "Untitled") if titles else "Untitled"

    authors: list[str] = []
    for creator in attrs.get("creators", []):
        given = creator.get("givenName", "").strip()
        family = creator.get("familyName", "").strip()
        if given and family:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
        else:
            # Fall back to the combined name field (DataCite often stores this
            # as "Family, Given" or "Family,Given"). Reorder to "Given Family".
            name = creator.get("name", "").strip()
            if name:
                if "," in name:
                    family_part, _, given_part = name.partition(",")
                    family_part = family_part.strip()
                    given_part = given_part.strip()
                    authors.append(f"{given_part} {family_part}" if given_part else family_part)
                else:
                    authors.append(name)

    year: int | None = None
    pub_year = attrs.get("publicationYear")
    if pub_year:
        try:
            year = int(pub_year)
        except (TypeError, ValueError):
            pass

    return {
        "doi": attrs.get("doi", doi),
        "title": title,
        "authors": authors,
        "year": year,
        "url": f"https://doi.org/{doi}",
        "openalex_id": None,
    }


async def resolve_doi(doi: str) -> dict[str, Any]:
    """
    Fetch metadata for *doi* from the Crossref REST API.

    Returns a normalized dict with keys:
        doi, title, authors, year, url, openalex_id

    Raises HTTPException(404) when the DOI is not found.
    Raises HTTPException(502) for unexpected upstream errors.
    """
    # Strip any leading https://doi.org/ that callers might pass.
    clean_doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if clean_doi.lower().startswith(prefix):
            clean_doi = clean_doi[len(prefix):]
            break

    url = f"{_BASE_URL}{clean_doi}"
    logger.debug("Crossref lookup: %s", url)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.get(url)
        except httpx.RequestError as exc:
            logger.error("Crossref request error for DOI %s: %s", doi, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach Crossref API.",
            ) from exc

    if response.status_code == 404:
        logger.debug(
            "Crossref 404 for DOI %s, trying DataCite + OpenAlex fallbacks", clean_doi
        )
        # Run both concurrently. DataCite is preferred for metadata (especially
        # author names) since it is authoritative for arXiv and institutional
        # repos and stores exact submission names. OpenAlex provides the
        # openalex_id needed for citation tracking.
        datacite_result, openalex_result = await asyncio.gather(
            _resolve_from_datacite(clean_doi),
            _resolve_from_openalex(clean_doi),
        )
        if datacite_result is not None:
            if openalex_result is not None:
                datacite_result["openalex_id"] = openalex_result.get("openalex_id")
            logger.info("Resolved DOI %s via DataCite fallback", clean_doi)
            return datacite_result
        if openalex_result is not None:
            logger.info("Resolved DOI %s via OpenAlex fallback", clean_doi)
            return openalex_result
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DOI not found in Crossref, OpenAlex, or DataCite: {doi}",
        )

    if response.status_code != 200:
        logger.error(
            "Crossref unexpected status %s for DOI %s", response.status_code, doi
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Crossref returned unexpected status {response.status_code}.",
        )

    payload = response.json()
    message: dict = payload.get("message", {})

    # Title is a list in Crossref; join if multiple parts.
    title_parts: list[str] = message.get("title", [])
    title = " ".join(title_parts).strip() if title_parts else "Untitled"

    return {
        "doi": message.get("DOI", clean_doi),
        "title": title,
        "authors": _extract_authors(message),
        "year": _extract_year(message),
        "url": message.get("URL", f"https://doi.org/{clean_doi}"),
        "openalex_id": None,  # Resolved separately via OpenAlex if needed.
    }

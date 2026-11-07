"""
OpenCitations Index client.

Docs: https://api.opencitations.net/index/v2

OpenCitations publishes the open reference lists deposited with Crossref and
other registries, so it lists citing papers for journals and proceedings
across every field. Each citation comes back as identifiers only (DOI,
OpenAlex ID, PubMed ID) plus the citing paper's publication date; titles and
authors are filled in afterwards from OpenAlex or Crossref.
"""

import logging
from typing import Any

import httpx

from citey.services import http_retry
from citey.services.source_errors import SourceUnavailable

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.opencitations.net/index/v2"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.email)"}


def _client(timeout: float) -> httpx.AsyncClient:
    from citey.config import get_settings

    headers = dict(_HEADERS)
    token = get_settings().opencitations_access_token
    if token:
        headers["authorization"] = token
    return httpx.AsyncClient(headers=headers, timeout=timeout)


def _clean_doi(doi: str) -> str:
    clean = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    return clean.lower()


def _parse_ids(field: str) -> dict[str, str]:
    """'omid:br/1 doi:10.1/x openalex:W1' -> {'omid': 'br/1', 'doi': '10.1/x', ...}"""
    out: dict[str, str] = {}
    for token in (field or "").split():
        scheme, _, value = token.partition(":")
        if value and scheme not in out:
            out[scheme] = value
    return out


def _on_or_after(date: str, since: str) -> bool:
    """Compare a possibly partial date ('2026', '2026-10') with a full one."""
    if not date:
        return True  # unknown date: let the metadata decide later
    return date >= since[: len(date)]


async def get_citing_refs(doi: str, since_date: str | None = None) -> list[dict[str, Any]]:
    """
    Every paper that cites *doi*, as identifier records.

    Returns dicts with ``doi`` (lowercase, may be None), ``openalex_id``
    (``https://openalex.org/W…`` or None), ``pmid`` and ``publication_date``
    (``creation``, which may be just a year or a month). Citations dated
    before *since_date* are dropped.

    Raises :class:`SourceUnavailable` when OpenCitations cannot answer.
    """
    clean = _clean_doi(doi)
    async with _client(timeout=60.0) as client:
        response = await http_retry.get_with_retry(
            client, f"{_BASE_URL}/citations/doi:{clean}", None,
            source="OpenCitations", context=clean,
        )
    if response is None or response.status_code != 200:
        status = response.status_code if response is not None else "no response"
        if status == 404:
            return []
        raise SourceUnavailable("opencitations", f"citations for {clean}: {status}")

    try:
        rows = response.json()
    except ValueError as exc:
        raise SourceUnavailable("opencitations", f"bad JSON for {clean}") from exc

    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows or []:
        ids = _parse_ids(row.get("citing", ""))
        date = (row.get("creation") or "").strip()
        if since_date and not _on_or_after(date, since_date):
            continue
        citing_doi = ids.get("doi", "").lower() or None
        oa = ids.get("openalex")
        key = citing_doi or oa or ids.get("omid") or ""
        if not key or key in seen or not (citing_doi or oa):
            continue
        seen.add(key)
        refs.append({
            "doi": citing_doi,
            "openalex_id": f"https://openalex.org/{oa}" if oa else None,
            "pmid": ids.get("pmid"),
            "publication_date": date or None,
        })

    logger.info("OpenCitations: %d citing record(s) for %s", len(refs), clean)
    return refs

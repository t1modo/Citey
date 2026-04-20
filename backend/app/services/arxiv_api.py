"""
arXiv API — fetch author names exactly as submitted by the authors.

Used to override abbreviated or garbled names from OpenAlex/Crossref
for papers whose DOI is in the 10.48550/arXiv.* namespace.
"""

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _extract_arxiv_id(doi: str) -> str | None:
    """Return the bare arXiv ID from a DOI like 10.48550/arXiv.2310.06825."""
    lower = doi.lower()
    prefix = "10.48550/arxiv."
    if lower.startswith(prefix):
        return doi[len(prefix):]
    return None


async def get_authors(doi: str) -> list[str]:
    """Return author names for an arXiv paper, exactly as submitted.

    Returns an empty list if the DOI is not an arXiv DOI, if the paper
    is not found, or on any network/parse error.
    """
    arxiv_id = _extract_arxiv_id(doi)
    if not arxiv_id:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_BASE_URL, params={"id_list": arxiv_id})
    except httpx.RequestError as exc:
        logger.warning("arXiv API request error for %s: %s", arxiv_id, exc)
        return []

    if response.status_code != 200:
        logger.warning("arXiv API status %s for %s", response.status_code, arxiv_id)
        return []

    try:
        root = ET.fromstring(response.text)
        ns = {"a": _ATOM_NS}
        entry = root.find("a:entry", ns)
        if entry is None:
            return []
        names = []
        for author in entry.findall("a:author", ns):
            name_el = author.find("a:name", ns)
            if name_el is not None and name_el.text:
                names.append(name_el.text.strip())
        return names
    except ET.ParseError as exc:
        logger.warning("arXiv API XML parse error for %s: %s", arxiv_id, exc)
        return []

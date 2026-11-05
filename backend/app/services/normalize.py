"""
Shared identifier and title normalisation.

DOI handling used to be reimplemented in several modules with different case
rules, which let the same paper be stored under two document IDs. Everything
that turns a DOI into a key should go through this module.
"""

import re
from difflib import SequenceMatcher
from typing import Iterable

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)

_TITLE_SIMILARITY = 0.85


def normalize_doi(doi: str | None) -> str | None:
    """Strip resolver prefixes and lowercase (DOIs are case-insensitive)."""
    if not doi:
        return None
    value = doi.strip()
    lowered = value.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            value = value[len(prefix):]
            break
    return value.strip().lower() or None


def doi_to_work_id(doi: str) -> str:
    """Firestore document ID for a tracked work (slashes are not allowed)."""
    return normalize_doi(doi).replace("/", "__")  # type: ignore[union-attr]


def is_arxiv_doi(doi: str | None) -> bool:
    return bool(doi and doi.lower().startswith("10.48550/arxiv"))


def norm_title(title: str | None) -> str:
    """Lowercase and strip punctuation for fuzzy comparison."""
    return re.sub(r"[^a-z0-9\s]", "", (title or "").lower()).strip()


def _similar(a: str, b: str) -> bool:
    matcher = SequenceMatcher(None, a, b)
    # Cheap upper bounds first; the full ratio is the expensive part.
    return (
        matcher.real_quick_ratio() >= _TITLE_SIMILARITY
        and matcher.quick_ratio() >= _TITLE_SIMILARITY
        and matcher.ratio() >= _TITLE_SIMILARITY
    )


def dedupe_works_by_title(raw_works: Iterable[dict]) -> list[dict]:
    """Keep one work per (near-)identical title, preferring non-arXiv DOIs.

    Works without a DOI or title are dropped since they can't be tracked.
    Order follows first appearance, so earlier sources win ties.
    """
    kept: dict[str, dict] = {}
    for raw in raw_works:
        doi = normalize_doi(raw.get("doi"))
        title = norm_title(raw.get("title"))
        if not doi or not title:
            continue

        match = title if title in kept else next(
            (k for k in kept if _similar(title, k)), None
        )
        if match is None:
            kept[title] = raw
            continue

        stored_doi = normalize_doi(kept[match].get("doi"))
        if is_arxiv_doi(stored_doi) and not is_arxiv_doi(doi):
            del kept[match]
            kept[title] = raw
    return list(kept.values())

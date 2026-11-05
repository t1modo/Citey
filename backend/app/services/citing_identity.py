"""
Recognise the same citing paper across sources, versions and nights.

A citing paper reaches Citey in several shapes: OpenAlex with a DOI,
Semantic Scholar without one, the arXiv preprint before the journal version,
or a record that gains its DOI a week later. Keying on DOI alone (falling back
to title) alerted the same paper twice in each of those cases.

Every citing paper therefore gets a set of identity keys, one per identifier
it has. Two records are the same paper when any key matches, and a paper has
been reported when any of its keys is in the work's ``notified_keys``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# Titles shorter than this, or with fewer words, are too generic to identify
# a paper on their own ("Editorial", "Reply to comment", "Introduction").
_TITLE_KEY_MIN_CHARS = 30
_TITLE_KEY_MIN_WORDS = 4

_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?(?:[?#].*)?$", re.IGNORECASE)
_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)

# Notices about other papers, not papers that cite yours.
# Matched only as a notice heading ("Erratum: ...", "Correction to ...", or the
# bare word), so research titles such as "Correction of lens aberrations" pass.
_JUNK_TITLE = re.compile(
    r"^\s*(?:correction|corrigendum|erratum|errata|addendum|retraction(?:\s+note|\s+notice)?"
    r"|retracted(?:\s+article)?|withdrawn|notice\s+of\s+retraction|(?:editorial\s+)?expression\s+of\s+concern"
    r"|publisher'?s?\s+note)"
    r"\s*(?::|\bto\b|\bfor\b|\bon\b|$)",
    re.IGNORECASE,
)
_JUNK_TYPES = frozenset({"erratum", "retraction", "paratext"})


def normalize_arxiv_id(value: str | None) -> str | None:
    """'arXiv:2506.02005v3' or 'hep-th/9901001' -> bare id without version."""
    if not value:
        return None
    text = value.strip()
    if text.lower().startswith("arxiv:"):
        text = text[6:]
    text = _ARXIV_VERSION.sub("", text.strip("/ "))
    return text.lower() or None


def arxiv_id_from_doi(doi: str | None) -> str | None:
    match = _ARXIV_DOI.match((doi or "").strip())
    return normalize_arxiv_id(match.group(1)) if match else None


def arxiv_id_from_url(url: str | None) -> str | None:
    match = _ARXIV_URL.search((url or "").strip())
    return normalize_arxiv_id(match.group(1)) if match else None


def title_key(title: str | None) -> str | None:
    """A normalised title, only when it is specific enough to identify a paper."""
    if not title or len(title.split()) < _TITLE_KEY_MIN_WORDS:
        return None
    nfkd = unicodedata.normalize("NFKD", title.lower())
    no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
    key = re.sub(r"[^\w]", "", no_marks, flags=re.UNICODE)
    return key if len(key) >= _TITLE_KEY_MIN_CHARS else None


def identity_keys(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    source_ids: Iterable[str | None] = (),
) -> set[str]:
    """Every key that identifies this citing paper."""
    keys: set[str] = set()
    doi_norm = (doi or "").strip().lower()
    if doi_norm:
        keys.add(f"doi:{doi_norm}")
    arxiv = normalize_arxiv_id(arxiv_id) or arxiv_id_from_doi(doi_norm)
    if arxiv:
        keys.add(f"arxiv:{arxiv}")
    tkey = title_key(title)
    if tkey:
        keys.add(f"title:{tkey}")
    for sid in source_ids:
        if sid:
            keys.add(f"id:{sid.strip().lower()}")
    return keys


def keys_for_normalized(item: dict[str, Any]) -> set[str]:
    """Identity keys for a citing work from either normaliser."""
    return identity_keys(
        doi=item.get("doi"),
        arxiv_id=item.get("arxiv_id"),
        title=item.get("title"),
        source_ids=[item.get("id")],
    )


def keys_for_raw_s2(raw: dict[str, Any]) -> set[str]:
    """Identity keys straight from a raw Semantic Scholar citing paper."""
    external = raw.get("externalIds") or {}
    paper_id = raw.get("paperId")
    return identity_keys(
        doi=external.get("DOI"),
        arxiv_id=external.get("ArXiv"),
        title=raw.get("title"),
        source_ids=[f"S2:{paper_id}" if paper_id else None],
    )


def is_junk(title: str | None, work_type: str | None = None) -> bool:
    """Corrections, retractions and similar notices are not citations."""
    if work_type and work_type.lower() in _JUNK_TYPES:
        return True
    return bool(title and _JUNK_TITLE.match(title))


def merge_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse records that share any identity key into one, in input order.

    The first record wins each field; later records only fill gaps (a DOI,
    affiliations, a date), so OpenAlex metadata is kept when it comes first.
    The merged record carries ``_keys``: the union of every member's keys.
    """
    merged: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for record in records:
        keys = keys_for_normalized(record)
        hits = sorted({index[k] for k in keys if k in index})
        if not hits:
            entry = {**record, "_keys": set(keys)}
            merged.append(entry)
            slot = len(merged) - 1
        else:
            slot = hits[0]
            entry = merged[slot]
            # A record can bridge two earlier entries (shares a DOI with one
            # and a title with another); fold the later ones into the first.
            for other in hits[1:]:
                _fill(entry, merged[other])
                merged[other] = {}
            _fill(entry, record)
            entry["_keys"] |= keys
        for k in entry["_keys"]:
            index[k] = slot
    return [m for m in merged if m]


def _fill(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field, value in source.items():
        if field == "_keys":
            target["_keys"] |= value
        elif value and not target.get(field):
            target[field] = value

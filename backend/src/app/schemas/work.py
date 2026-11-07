"""API shapes for tracked papers: what /api/works returns and accepts."""

import re
from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.services.text_clean import clean_names, clean_text


_OPENALEX_WORK_RE = re.compile(r"^(?:https://openalex\.org/)?W\d+$")


def is_openalex_work_id(value: Optional[str]) -> bool:
    """True for a real OpenAlex work ID (``W123`` or ``https://openalex.org/W123``).

    Imports from other sources used to store their own IDs (``S2:…``,
    ``pubmed:…``, ``dblp:…``) in the ``openalex_id`` field; those must never
    be sent to OpenAlex.
    """
    return bool(value) and bool(_OPENALEX_WORK_RE.match(value))


class TrackedWork(SQLModel):
    id: str  # DOI or OpenAlex ID used as the work's key
    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None          # journal / conference / repository name
    work_type: Optional[str] = None      # "journal-article", "conference-paper", "preprint", …
    topics: list[str] = Field(default_factory=list)  # subject tags from OpenAlex
    added_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    citation_count: int = 0
    new_citations_30d: int = 0
    s2_citation_count: Optional[int] = None
    openalex_citation_count: Optional[int] = None

    @field_validator("openalex_id")
    @classmethod
    def _real_openalex_id(cls, v: Optional[str]) -> Optional[str]:
        return v if is_openalex_work_id(v) else None

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        return clean_text(v) or ""

    @field_validator("venue")
    @classmethod
    def _clean_venue(cls, v: Optional[str]) -> Optional[str]:
        return clean_text(v) or None

    @field_validator("authors")
    @classmethod
    def _clean_authors(cls, v: list[str]) -> list[str]:
        return clean_names(v)


class AddWorkRequest(SQLModel):
    doi: str = Field(..., max_length=300)
    force: bool = False  # bypass author-presence check


class ImportByAuthorRequest(SQLModel):
    author_id: str = Field(..., max_length=300)
    author_name: Optional[str] = Field(default=None, max_length=200)
    source: str = "openalex"  # "openalex" | "semantic_scholar" | "inspire" | "dblp"
    confirm_merge: bool = False  # user confirmed two profiles belong to the same person
    # Cross-source boosts to enable. Empty = primary source only (safe default).
    # Valid values: "openalex", "semantic_scholar", "pubmed", "nasa_ads", "inspire", "dblp"
    extra_sources: list[str] = Field(default_factory=list, max_length=6)

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class LinkedAuthorEntry(BaseModel):
    id: str
    name: Optional[str] = None


class UserProfile(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    notification_email: Optional[str] = None
    notify_enabled: bool = True
    notify_new_publications: bool = True
    scholar_url: Optional[str] = None
    linked_author_id: Optional[str] = None
    linked_author_name: Optional[str] = None
    additional_linked_authors: list[LinkedAuthorEntry] = Field(default_factory=list)
    name_aliases: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class TrackedWork(BaseModel):
    id: str  # DOI or OpenAlex ID used as the Firestore doc ID
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


class Notification(BaseModel):
    id: str
    cited_work_id: str
    cited_work_title: str
    citing_work_id: str
    citing_work_title: str
    citing_work_doi: Optional[str] = None
    citing_work_url: Optional[str] = None
    citing_authors: list[str] = Field(default_factory=list)
    citing_affiliations: list[str] = Field(default_factory=list)
    citing_year: Optional[int] = None
    citing_publication_date: Optional[str] = None
    seen: bool = False
    created_at: Optional[datetime] = None


class AddWorkRequest(BaseModel):
    doi: str = Field(..., max_length=300)
    force: bool = False  # bypass author-presence check


class ImportByAuthorRequest(BaseModel):
    author_id: str = Field(..., max_length=300)
    author_name: Optional[str] = Field(default=None, max_length=200)
    source: str = "openalex"  # "openalex" | "semantic_scholar" | "inspire" | "dblp"
    confirm_merge: bool = False  # user confirmed two profiles belong to the same person
    # Cross-source boosts to enable. Empty = primary source only (safe default).
    # Valid values: "openalex", "semantic_scholar", "pubmed", "nasa_ads", "inspire", "dblp"
    extra_sources: list[str] = Field(default_factory=list, max_length=6)


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    notification_email: Optional[str] = Field(default=None, max_length=254)
    notify_enabled: Optional[bool] = None
    notify_new_publications: Optional[bool] = None
    scholar_url: Optional[str] = Field(default=None, max_length=500)
    name_aliases: Optional[list[str]] = None

    @field_validator("notification_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address.")
        return v

    @field_validator("scholar_url")
    @classmethod
    def validate_scholar_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not _URL_RE.match(v):
            raise ValueError("Scholar URL must start with http:// or https://.")
        return v

    @field_validator("name_aliases")
    @classmethod
    def validate_aliases(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 name aliases allowed.")
        for alias in v:
            if len(alias) > 100:
                raise ValueError("Each alias must be 100 characters or fewer.")
        return v


class PaginatedNotifications(BaseModel):
    items: list["Notification"]
    total: int
    unseen: int
    page: int
    limit: int
    pages: int


class JobRunRequest(BaseModel):
    dry_run: bool = False

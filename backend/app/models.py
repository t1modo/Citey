from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    notification_email: Optional[str] = None
    notify_enabled: bool = True
    scholar_url: Optional[str] = None
    linked_author_id: Optional[str] = None
    linked_author_name: Optional[str] = None
    name_aliases: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class TrackedWork(BaseModel):
    id: str  # DOI or OpenAlex ID used as the Firestore doc ID
    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
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
    doi: str
    force: bool = False  # bypass author-presence check


class ImportByAuthorRequest(BaseModel):
    author_id: str
    author_name: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    notification_email: Optional[str] = None
    notify_enabled: Optional[bool] = None
    scholar_url: Optional[str] = None
    name_aliases: Optional[list[str]] = None


class PaginatedNotifications(BaseModel):
    items: list["Notification"]
    total: int
    unseen: int
    page: int
    limit: int
    pages: int


class JobRunRequest(BaseModel):
    dry_run: bool = False

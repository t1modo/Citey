"""API shapes for citation alerts (/api/notifications)."""

from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.services.text_clean import clean_names, clean_text


class Notification(SQLModel):
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
    # False until the alert email for it has actually been sent, so a failed
    # send is retried on the next run instead of being lost.
    emailed: bool = False
    created_at: Optional[datetime] = None

    @field_validator("cited_work_title", "citing_work_title")
    @classmethod
    def _clean_titles(cls, v: str) -> str:
        return clean_text(v) or ""

    @field_validator("citing_authors")
    @classmethod
    def _clean_authors(cls, v: list[str]) -> list[str]:
        return clean_names(v)

    @field_validator("citing_affiliations")
    @classmethod
    def _clean_affiliations(cls, v: list[str]) -> list[str]:
        return [a for a in (clean_text(x) for x in v) if a]


class PaginatedNotifications(SQLModel):
    items: list["Notification"]
    total: int
    unseen: int
    page: int
    limit: int
    pages: int

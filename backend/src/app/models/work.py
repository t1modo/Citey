"""Papers people track (``works``) and who tracks them (``user_works``)."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Integer, Text
from sqlmodel import Field, Relationship

from app.models.base import Base, bigint_pk_column, created_at_column, text_array_column, timestamp_column
from app.models.user import User

if TYPE_CHECKING:
    from app.models.citation import Citation


class Work(Base, table=True):
    """
    One paper, shared by everyone who tracks it.
    """

    __tablename__ = "works"

    id: Optional[int] = bigint_pk_column()
    # The ID Citey already uses for a paper: its lowercased DOI, or its
    # OpenAlex ID when it has no DOI.
    key: str = Field(unique=True, nullable=False, sa_type=Text)
    doi: Optional[str] = Field(default=None, unique=True, sa_type=Text)
    openalex_id: Optional[str] = Field(default=None, index=True, sa_type=Text)

    title: str = Field(nullable=False, sa_type=Text)
    authors: list[str] = text_array_column()
    year: Optional[int] = Field(default=None, sa_type=Integer)
    venue: Optional[str] = Field(default=None, sa_type=Text)
    work_type: Optional[str] = Field(default=None, sa_type=Text)
    topics: list[str] = text_array_column()

    # Lifetime totals from the indexes.
    openalex_citation_count: Optional[int] = Field(default=None, sa_type=Integer)
    s2_citation_count: Optional[int] = Field(default=None, sa_type=Integer)

    # Nightly check state, now kept once per paper rather than per user.
    last_checked_at: Optional[datetime] = timestamp_column()
    last_check_failed_sources: list[str] = text_array_column()
    # Version of the "what counts as new" window the first check recorded
    # citations under.
    citation_window: Optional[int] = Field(default=None, sa_type=Integer)
    # Identity keys ("doi:…", "id:w…") of citing papers reported without
    # their details being kept. They count as already reported, so those
    # papers are never announced twice.
    known_citing_keys: list[str] = text_array_column()

    created_at: datetime = created_at_column()

    trackers: list["UserWork"] = Relationship(back_populates="work")
    citations: list["Citation"] = Relationship(
        back_populates="work", sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )


class UserWork(Base, table=True):
    """A user tracks a paper."""

    __tablename__ = "user_works"

    user_id: str = Field(
        primary_key=True, foreign_key="users.id", ondelete="CASCADE", max_length=128
    )
    work_id: int = Field(
        primary_key=True, foreign_key="works.id", ondelete="CASCADE", sa_type=BigInteger, index=True
    )
    # Citations found before this are the baseline, not news, for this user.
    added_at: datetime = created_at_column()

    user: User = Relationship(back_populates="tracked")
    work: Work = Relationship(back_populates="trackers")

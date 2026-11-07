"""Papers that cite tracked ones (``citing_works``, ``citing_work_keys``) and
who cites what (``citations``)."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, Integer, Text, UniqueConstraint
from sqlmodel import Field, Relationship

from app.models.base import Base, bigint_pk_column, cascade_fk_column, created_at_column, text_array_column
from app.models.work import Work

if TYPE_CHECKING:
    from app.models.alert import Alert


class CitingWork(Base, table=True):
    """
    A paper that cites a tracked one, stored once. Firestore copies its
    details into every alert as citing_work_*.
    """

    __tablename__ = "citing_works"

    id: Optional[int] = bigint_pk_column()
    # Canonical identity: the lowercased DOI, else the source's own ID.
    key: str = Field(unique=True, nullable=False, sa_type=Text)
    doi: Optional[str] = Field(default=None, index=True, sa_type=Text)
    openalex_id: Optional[str] = Field(default=None, index=True, sa_type=Text)
    url: Optional[str] = Field(default=None, sa_type=Text)
    title: str = Field(nullable=False, sa_type=Text)
    authors: list[str] = text_array_column()
    affiliations: list[str] = text_array_column()
    year: Optional[int] = Field(default=None, sa_type=Integer)
    # As the source gives it: "2025", "2025-03" or "2025-03-14".
    publication_date: Optional[str] = Field(default=None, sa_type=Text)
    created_at: datetime = created_at_column()

    keys: list["CitingWorkKey"] = Relationship(
        back_populates="citing_work", sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )
    citations: list["Citation"] = Relationship(back_populates="citing_work")


class CitingWorkKey(Base, table=True):
    """
    Every identity a citing paper is known by ("doi:…", "id:w123…"), so the
    same paper reported by OpenAlex, Semantic Scholar, OpenCitations and
    Europe PMC is recognised as one. Firestore: notified_keys.
    """

    __tablename__ = "citing_work_keys"

    key: str = Field(primary_key=True, sa_type=Text)
    citing_work_id: int = cascade_fk_column("citing_works.id")

    citing_work: CitingWork = Relationship(back_populates="keys")

    __table_args__ = (Index(None, "citing_work_id"),)


class Citation(Base, table=True):
    """Paper ``citing_work`` cites tracked paper ``work``. Recorded once."""

    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("work_id", "citing_work_id"),
        Index(None, "citing_work_id"),
    )

    id: Optional[int] = bigint_pk_column()
    work_id: int = cascade_fk_column("works.id")
    citing_work_id: int = cascade_fk_column("citing_works.id")
    found_at: datetime = created_at_column()

    work: Work = Relationship(back_populates="citations")
    citing_work: CitingWork = Relationship(back_populates="citations")
    alerts: list["Alert"] = Relationship(
        back_populates="citation", sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )

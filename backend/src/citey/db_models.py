"""
Postgres tables, as SQLModel models (SQLAlchemy 2.1 ORM tables that are also
Pydantic models).

Firestore keeps a copy of every paper under each user who tracks it, and a
copy of each citing paper inside every alert. Here a paper is one row in
``works`` however many people track it, a citing paper is one row in
``citing_works``, and "A cites B" is one row in ``citations``. What differs
per user (who tracks what, and which alerts they have seen or been emailed)
lives in ``user_works`` and ``alerts``.

    users ─< user_works >─ works ─< citations >─ citing_works ─< citing_work_keys
      └──────────< alerts >───────────┘

The API's request and response shapes stay in ``app.models``; these are the
storage layer only. Change a table here, then generate a migration:

    uv run alembic revision --autogenerate -m "what changed"
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, Relationship, SQLModel

# Deterministic constraint names, so Alembic migrations name them the same
# way on every machine and can drop them later.
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Column helpers. Each call builds a new Field, since a column belongs to
# exactly one table. Every default is set both in Python (for objects built
# in code) and in the database (for rows written by migrations or psql).


def _created_at() -> Any:
    return Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("now()")},
    )


def _timestamp() -> Any:
    return Field(default=None, sa_type=DateTime(timezone=True))


def _text_array() -> Any:
    return Field(
        default_factory=list,
        nullable=False,
        sa_type=ARRAY(Text),
        sa_column_kwargs={"server_default": text("'{}'::text[]")},
    )


def _flag(default: bool) -> Any:
    return Field(
        default=default,
        nullable=False,
        sa_type=Boolean,
        sa_column_kwargs={"server_default": text("true" if default else "false")},
    )


def _bigint_pk() -> Any:
    return Field(default=None, primary_key=True, sa_type=BigInteger)


def _fk(target: str) -> Any:
    """A required BIGINT foreign key that disappears with its parent row."""
    return Field(foreign_key=target, ondelete="CASCADE", nullable=False, sa_type=BigInteger)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    """One account. Firestore: ``users/{uid}``."""

    __tablename__ = "users"

    # The Firebase UID, or the Clerk user ID for someone who signed up with
    # Clerk. A user imported into Clerk keeps their Firebase UID as Clerk's
    # external_id, so their rows stay theirs.
    id: str = Field(primary_key=True, max_length=128)
    email: str = Field(
        default="", nullable=False, sa_type=Text, sa_column_kwargs={"server_default": text("''")}
    )
    display_name: Optional[str] = Field(default=None, sa_type=Text)

    # Alerts go to notification_email once it is confirmed, and to the
    # account email until then.
    notification_email: Optional[str] = Field(default=None, sa_type=Text)
    verified_notification_email: Optional[str] = Field(default=None, sa_type=Text)
    notify_enabled: bool = _flag(True)
    notify_new_publications: bool = _flag(True)

    scholar_url: Optional[str] = Field(default=None, sa_type=Text)
    # The author profile (OpenAlex, Semantic Scholar, INSPIRE or DBLP ID)
    # whose papers this user tracks, plus any profiles merged into it as
    # [{"id": ..., "name": ...}].
    linked_author_id: Optional[str] = Field(default=None, sa_type=Text, index=True)
    linked_author_name: Optional[str] = Field(default=None, sa_type=Text)
    additional_linked_authors: list[dict[str, Any]] = Field(
        default_factory=list,
        nullable=False,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'[]'::jsonb")},
    )
    name_aliases: list[str] = _text_array()
    # works.key values the user removed, so publication sync doesn't add
    # them back. Firestore: dismissed_work_ids.
    dismissed_work_keys: list[str] = _text_array()

    # Cooldowns and bookkeeping.
    last_import_at: Optional[datetime] = _timestamp()
    last_manual_check_at: Optional[datetime] = _timestamp()
    last_manual_sync_at: Optional[datetime] = _timestamp()
    last_publication_sync_at: Optional[datetime] = _timestamp()
    last_email_test_at: Optional[datetime] = _timestamp()
    last_verification_email_at: Optional[datetime] = _timestamp()
    last_confirm_email_at: Optional[datetime] = _timestamp()

    created_at: datetime = _created_at()

    tracked: list["UserWork"] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    alerts: list["Alert"] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ---------------------------------------------------------------------------
# Papers people track
# ---------------------------------------------------------------------------


class Work(SQLModel, table=True):
    """
    One paper, shared by everyone who tracks it. Firestore copies it into
    ``users/{uid}/trackedWorks/{key}`` once per user.
    """

    __tablename__ = "works"

    id: Optional[int] = _bigint_pk()
    # The ID Citey already uses for a paper: its lowercased DOI, or its
    # OpenAlex ID when it has no DOI. Firestore's trackedWorks document ID.
    key: str = Field(unique=True, nullable=False, sa_type=Text)
    doi: Optional[str] = Field(default=None, unique=True, sa_type=Text)
    openalex_id: Optional[str] = Field(default=None, index=True, sa_type=Text)

    title: str = Field(nullable=False, sa_type=Text)
    authors: list[str] = _text_array()
    year: Optional[int] = Field(default=None, sa_type=Integer)
    venue: Optional[str] = Field(default=None, sa_type=Text)
    work_type: Optional[str] = Field(default=None, sa_type=Text)
    topics: list[str] = _text_array()

    # Lifetime totals from the indexes.
    openalex_citation_count: Optional[int] = Field(default=None, sa_type=Integer)
    s2_citation_count: Optional[int] = Field(default=None, sa_type=Integer)

    # Nightly check state, now kept once per paper rather than per user.
    last_checked_at: Optional[datetime] = _timestamp()
    last_check_failed_sources: list[str] = _text_array()
    # Version of the "what counts as new" window the first check recorded
    # citations under. Firestore: citation_window.
    citation_window: Optional[int] = Field(default=None, sa_type=Integer)

    created_at: datetime = _created_at()

    trackers: list["UserWork"] = Relationship(back_populates="work")
    citations: list["Citation"] = Relationship(
        back_populates="work", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class UserWork(SQLModel, table=True):
    """A user tracks a paper."""

    __tablename__ = "user_works"

    user_id: str = Field(
        primary_key=True, foreign_key="users.id", ondelete="CASCADE", max_length=128
    )
    work_id: int = Field(
        primary_key=True, foreign_key="works.id", ondelete="CASCADE", sa_type=BigInteger, index=True
    )
    # Citations found before this are the baseline, not news, for this user.
    added_at: datetime = _created_at()

    user: User = Relationship(back_populates="tracked")
    work: Work = Relationship(back_populates="trackers")


# ---------------------------------------------------------------------------
# Papers that cite them
# ---------------------------------------------------------------------------


class CitingWork(SQLModel, table=True):
    """
    A paper that cites a tracked one, stored once. Firestore copies its
    details into every alert as citing_work_*.
    """

    __tablename__ = "citing_works"

    id: Optional[int] = _bigint_pk()
    # Canonical identity: the lowercased DOI, else the source's own ID.
    key: str = Field(unique=True, nullable=False, sa_type=Text)
    doi: Optional[str] = Field(default=None, index=True, sa_type=Text)
    openalex_id: Optional[str] = Field(default=None, index=True, sa_type=Text)
    url: Optional[str] = Field(default=None, sa_type=Text)
    title: str = Field(nullable=False, sa_type=Text)
    authors: list[str] = _text_array()
    affiliations: list[str] = _text_array()
    year: Optional[int] = Field(default=None, sa_type=Integer)
    # As the source gives it: "2025", "2025-03" or "2025-03-14".
    publication_date: Optional[str] = Field(default=None, sa_type=Text)
    created_at: datetime = _created_at()

    keys: list["CitingWorkKey"] = Relationship(
        back_populates="citing_work", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    citations: list["Citation"] = Relationship(back_populates="citing_work")


class CitingWorkKey(SQLModel, table=True):
    """
    Every identity a citing paper is known by ("doi:…", "id:w123…"), so the
    same paper reported by OpenAlex, Semantic Scholar, OpenCitations and
    Europe PMC is recognised as one. Firestore: notified_keys.
    """

    __tablename__ = "citing_work_keys"

    key: str = Field(primary_key=True, sa_type=Text)
    citing_work_id: int = _fk("citing_works.id")

    citing_work: CitingWork = Relationship(back_populates="keys")

    __table_args__ = (Index(None, "citing_work_id"),)


class Citation(SQLModel, table=True):
    """Paper ``citing_work`` cites tracked paper ``work``. Recorded once."""

    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("work_id", "citing_work_id"),
        Index(None, "citing_work_id"),
    )

    id: Optional[int] = _bigint_pk()
    work_id: int = _fk("works.id")
    citing_work_id: int = _fk("citing_works.id")
    found_at: datetime = _created_at()

    work: Work = Relationship(back_populates="citations")
    citing_work: CitingWork = Relationship(back_populates="citations")
    alerts: list["Alert"] = Relationship(
        back_populates="citation", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class Alert(SQLModel, table=True):
    """
    A citation as one user sees it. Firestore: ``users/{uid}/notifications``.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "citation_id"),
        Index(None, "user_id", "created_at"),
        Index(None, "citation_id"),
        # Small indexes for the two "what's left" queries.
        Index("ix_alerts_unseen", "user_id", postgresql_where=text("NOT seen")),
        Index("ix_alerts_unemailed", "user_id", postgresql_where=text("NOT emailed")),
    )

    id: Optional[int] = _bigint_pk()
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", nullable=False, max_length=128)
    citation_id: int = _fk("citations.id")
    seen: bool = _flag(False)
    # False until the alert email was actually sent, so a failed send is
    # retried on the next run instead of being lost.
    emailed: bool = _flag(False)
    created_at: datetime = _created_at()

    user: User = Relationship(back_populates="alerts")
    citation: Citation = Relationship(back_populates="alerts")


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


class SupportLimit(SQLModel, table=True):
    """
    Contact form use per hashed IP or email in the current window.
    Firestore: ``supportLimits/{key}``.
    """

    __tablename__ = "support_limits"

    key: str = Field(primary_key=True, sa_type=Text)
    window_start: datetime = Field(nullable=False, sa_type=DateTime(timezone=True))
    count: int = Field(default=0, nullable=False, sa_type=Integer)

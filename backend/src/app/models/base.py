"""
What every table shares: the Base class, constraint naming, and column
helpers that set each default both in Python (for objects built in code) and
in the database (for rows written by migrations or plain SQL).
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

# Deterministic constraint names, so Alembic migrations name them the same
# way on every machine and can drop them later.
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(SQLModel):
    """Every table subclasses this: ``class User(Base, table=True)``."""


metadata = Base.metadata


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Relationships that own children (cascade "all, delete-orphan") also set
# passive_deletes: the database's ON DELETE CASCADE removes the children, so
# deleting a parent never has to load them first, which async code can't do
# lazily.

# Each helper builds a new Field, since a column belongs to exactly one table.


def created_at_column() -> Any:
    """Set when the row is written."""
    return Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("now()")},
    )


def timestamp_column() -> Any:
    """An optional moment, with time zone."""
    return Field(default=None, sa_type=DateTime(timezone=True))


def text_array_column() -> Any:
    """A list of strings, empty by default."""
    return Field(
        default_factory=list,
        nullable=False,
        sa_type=ARRAY(Text),
        sa_column_kwargs={"server_default": text("'{}'::text[]")},
    )


def flag_column(default: bool) -> Any:
    """A required boolean."""
    return Field(
        default=default,
        nullable=False,
        sa_type=Boolean,
        sa_column_kwargs={"server_default": text("true" if default else "false")},
    )


def bigint_pk_column() -> Any:
    """A BIGINT primary key the database assigns."""
    return Field(default=None, primary_key=True, sa_type=BigInteger)


def cascade_fk_column(target: str) -> Any:
    """A required BIGINT foreign key that disappears with its parent row."""
    return Field(foreign_key=target, ondelete="CASCADE", nullable=False, sa_type=BigInteger)

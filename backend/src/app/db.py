"""
Neon Postgres access.

The API runs as Vercel Functions, so each request opens a short-lived
connection through Neon's pooler (the pooled DATABASE_URL) instead of
holding a pool of its own. The pooler runs PgBouncer in transaction mode,
which does not support server-side prepared statements, so psycopg's
automatic prepare is turned off.

Two ways in, over the same psycopg driver: ``connect()`` for raw SQL, and
``get_session()`` for the SQLModel / SQLAlchemy ORM tables in
``app.models``.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import psycopg
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session

from app.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set."""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=10) as conn:
        yield conn


def sqlalchemy_url(url: str) -> str:
    """
    Neon hands out ``postgresql://`` (or ``postgres://``) URLs; SQLAlchemy
    needs the driver named to use psycopg 3 rather than psycopg2.
    """
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    """
    An engine that keeps no connections of its own (NullPool): the pooler
    already pools, and a Vercel Function would only hold idle connections
    between requests. Prepared statements are off, as the pooler requires.
    """
    return create_engine(
        sqlalchemy_url(url),
        poolclass=NullPool,
        connect_args={"prepare_threshold": None, "connect_timeout": 10},
    )


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    return make_engine(url)


def get_session() -> Iterator[Session]:
    """
    FastAPI dependency: one ORM session per request, closed afterwards.
    Commit explicitly; anything uncommitted is rolled back on close.

        def handler(session: Session = Depends(get_session)): ...
    """
    with Session(get_engine()) as session:
        yield session


def check() -> dict:
    """
    Prove the database works end to end: connect, write a row and read it
    back inside a transaction that is rolled back, so nothing is left behind.
    """
    started = time.perf_counter()
    with connect() as conn:
        with conn.transaction(force_rollback=True), conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('server_version')")
            database, server_version = cur.fetchone()
            cur.execute("CREATE TEMP TABLE citey_health (note text) ON COMMIT DROP")
            cur.execute("INSERT INTO citey_health (note) VALUES (%s) RETURNING note", ("ok",))
            written = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM citey_health WHERE note = %s", ("ok",))
            read_back = cur.fetchone()[0]
    return {
        "database": database,
        "server_version": server_version,
        "write_read_ok": written == "ok" and read_back == 1,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }

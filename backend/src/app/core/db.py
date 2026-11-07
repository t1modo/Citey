"""
Neon Postgres access, async throughout.

The API runs as Vercel Functions, so each request opens a short-lived
connection through Neon's pooler (the pooled DATABASE_URL) instead of
holding a pool of its own. The pooler runs PgBouncer in transaction mode,
which does not support server-side prepared statements, so psycopg's
automatic prepare is turned off.

Two ways in, over the same async psycopg driver:

    async with connect() as conn:            raw SQL (psycopg.AsyncConnection)
        ...

    async def handler(session: AsyncSession = Depends(get_session)):
        rows = (await session.exec(select(Work))).all()   # the app.models tables

Nothing here blocks the event loop. Relationships are not loaded lazily in
async code: load what you need up front, e.g.
``select(Alert).options(selectinload(Alert.citation))``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set."""


def _database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    return url


@asynccontextmanager
async def connect() -> AsyncIterator[psycopg.AsyncConnection]:
    """A raw async psycopg connection, closed on exit."""
    conn = await psycopg.AsyncConnection.connect(
        _database_url(), prepare_threshold=None, connect_timeout=10
    )
    async with conn:
        yield conn


def sqlalchemy_url(url: str) -> str:
    """
    Neon hands out ``postgresql://`` (or ``postgres://``) URLs; SQLAlchemy
    needs the driver named to use psycopg 3 rather than psycopg2. With an
    async engine the same URL selects psycopg's async mode.
    """
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> AsyncEngine:
    """
    An async engine that keeps no connections of its own (NullPool): the
    pooler already pools, and a Vercel Function would only hold idle
    connections between requests. Prepared statements are off, as the pooler
    requires.
    """
    return create_async_engine(
        sqlalchemy_url(url),
        poolclass=NullPool,
        connect_args={"prepare_threshold": None, "connect_timeout": 10},
    )


@lru_cache
def get_engine() -> AsyncEngine:
    return make_engine(_database_url())


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency: one async ORM session per request, closed afterwards.
    Commit explicitly; anything uncommitted is rolled back on close. Objects
    stay readable after a commit (expire_on_commit=False), since reloading an
    expired attribute would need an await.
    """
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session


async def check() -> dict:
    """
    Prove the database works end to end: connect, write a row and read it
    back inside a transaction that is rolled back, so nothing is left behind.
    """
    started = time.perf_counter()
    async with connect() as conn:
        async with conn.transaction(force_rollback=True), conn.cursor() as cur:
            await cur.execute("SELECT current_database(), current_setting('server_version')")
            database, server_version = await cur.fetchone()
            await cur.execute("CREATE TEMP TABLE citey_health (note text) ON COMMIT DROP")
            await cur.execute("INSERT INTO citey_health (note) VALUES (%s) RETURNING note", ("ok",))
            written = (await cur.fetchone())[0]
            await cur.execute("SELECT count(*) FROM citey_health WHERE note = %s", ("ok",))
            read_back = (await cur.fetchone())[0]
    return {
        "database": database,
        "server_version": server_version,
        "write_read_ok": written == "ok" and read_back == 1,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """An async ORM session outside a request (jobs, scripts), closed on exit."""
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session

"""
Neon Postgres access.

The API runs as Vercel Functions, so each request opens a short-lived
connection through Neon's pooler (the pooled DATABASE_URL) instead of
holding a pool of its own. The pooler runs PgBouncer in transaction mode,
which does not support server-side prepared statements, so psycopg's
automatic prepare is turned off.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

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

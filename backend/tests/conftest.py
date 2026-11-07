"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Skip real waiting in the source clients' retry and throttle loops."""

    async def _instant(_seconds: float) -> None:
        return None

    from app.services import openalex, semantic_scholar

    monkeypatch.setattr(openalex, "_sleep", _instant)
    monkeypatch.setattr(semantic_scholar, "_sleep", _instant, raising=False)


@pytest.fixture(autouse=True)
def _quiet_extra_citation_sources(monkeypatch, request):
    """OpenCitations and Europe PMC answer "no citations" unless a test
    patches them, so tests written for OpenAlex and S2 never reach the
    network. Tests of the clients themselves opt out with the marker."""
    from app.services import http_retry

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "_sleep", _instant)
    if request.node.get_closest_marker("real_extra_sources"):
        return

    from unittest.mock import AsyncMock

    from app.services import citation_service

    monkeypatch.setattr(citation_service.opencitations_svc, "get_citing_refs", AsyncMock(return_value=[]))
    monkeypatch.setattr(citation_service.europe_pmc_svc, "get_citing_works", AsyncMock(return_value=[]))


# ---------------------------------------------------------------------------
# Postgres: a throwaway database for tests marked with `needs_db`.
# ---------------------------------------------------------------------------

import os as _os
from pathlib import Path as _Path
from urllib.parse import urlsplit as _urlsplit

TEST_DATABASE_URL = _os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to a throwaway Postgres")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "::1"}


def alembic_config():
    from alembic.config import Config

    cfg = Config(str(_Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated():
    """The schema, rebuilt once per run (down and up again, so the downgrade
    is exercised too). Only local hosts: the database is wiped."""
    from alembic import command

    from app.core.db import sqlalchemy_url

    host = _urlsplit(sqlalchemy_url(TEST_DATABASE_URL)).hostname
    if host not in _LOCAL_HOSTS:
        pytest.fail(f"TEST_DATABASE_URL must point at a local throwaway database, not {host!r}")
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture
async def pg_session(migrated):
    """An AsyncSession on the test database; every table is emptied afterwards."""
    from sqlalchemy import inspect, text
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.db import make_engine

    engine = make_engine(TEST_DATABASE_URL)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    async with engine.begin() as conn:
        tables = await conn.run_sync(
            lambda c: [t for t in inspect(c).get_table_names() if t != "alembic_version"]
        )
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await engine.dispose()

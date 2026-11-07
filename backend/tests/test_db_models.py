"""
The Postgres schema: migrations, constraints and ORM relationships, through
the same async engine and AsyncSession the app uses.

These need a real, throwaway Postgres. They run when TEST_DATABASE_URL is
set (CI starts one; locally `docker compose up -d postgres` and use
postgresql://citey:citey@localhost:5432/citey_test) and are skipped
otherwise. The schema is dropped and rebuilt, so only local hosts are
accepted.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import DatabaseNotConfigured, make_engine, sqlalchemy_url
from app.models import (
    Alert,
    Citation,
    CitingWork,
    CitingWorkKey,
    User,
    UserWork,
    Work,
)

BACKEND = Path(__file__).resolve().parent.parent
TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "::1"}

needs_db = pytest.mark.skipif(not TEST_URL, reason="set TEST_DATABASE_URL to a throwaway Postgres")


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="module")
def migrated():
    """Rebuild the schema once per module: down and up again, so the
    downgrade is exercised too. Alembic runs its own event loop, so this
    fixture is synchronous."""
    host = urlsplit(sqlalchemy_url(TEST_URL)).hostname
    if host not in _LOCAL_HOSTS:
        pytest.fail(f"TEST_DATABASE_URL must point at a local throwaway database, not {host!r}")
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture
async def session(migrated):
    engine = make_engine(TEST_URL)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    async with engine.begin() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: [t for t in inspect(sync_conn).get_table_names() if t != "alembic_version"]
        )
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await engine.dispose()


def _paper(key: str = "10.1234/abc", **kw) -> Work:
    return Work(key=key, doi=key, title=kw.pop("title", "Attention Is All You Need"), **kw)


def _citing(key: str = "10.9999/cites", **kw) -> CitingWork:
    return CitingWork(key=key, doi=key, title=kw.pop("title", "A Paper That Cites It"), **kw)


# --- No database needed ------------------------------------------------------


def test_neon_urls_use_the_psycopg_driver() -> None:
    url = "postgresql://u:p@ep-x-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
    assert sqlalchemy_url(url) == (
        "postgresql+psycopg://u:p@ep-x-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
    )
    assert sqlalchemy_url("postgres://u@h/db") == "postgresql+psycopg://u@h/db"
    assert sqlalchemy_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"


async def test_session_needs_a_database_url(monkeypatch) -> None:
    from app.config import Settings
    from app.core import db

    monkeypatch.setattr(db, "get_settings", lambda: Settings(database_url=""))
    db.get_engine.cache_clear()
    with pytest.raises(DatabaseNotConfigured):
        await anext(db.get_session())
    db.get_engine.cache_clear()


# --- Against Postgres --------------------------------------------------------


@needs_db
def test_migrations_match_the_models(migrated) -> None:
    # Raises if a table in app/models/ changed without a new migration.
    command.check(_alembic_config())


@needs_db
async def test_a_paper_is_stored_once_however_many_people_track_it(session) -> None:
    paper = _paper()
    for uid in ("ada", "grace", "alan"):
        session.add(User(id=uid, email=f"{uid}@uni.edu"))
        session.add(UserWork(user_id=uid, work=paper))
    await session.commit()

    works = (await session.exec(select(Work).options(selectinload(Work.trackers)))).all()
    assert works == [paper]
    assert sorted(t.user_id for t in works[0].trackers) == ["ada", "alan", "grace"]


@needs_db
async def test_a_new_citation_becomes_one_alert_per_tracker(session) -> None:
    paper = _paper()
    ada, grace = User(id="ada", email="ada@uni.edu"), User(id="grace", email="g@uni.edu")
    session.add_all([UserWork(user=ada, work=paper), UserWork(user=grace, work=paper)])
    citing = _citing(authors=["Barbara Liskov"], affiliations=["MIT"])
    citing.keys = [CitingWorkKey(key="doi:10.9999/cites"), CitingWorkKey(key="id:w42")]
    citation = Citation(work=paper, citing_work=citing)
    session.add_all([Alert(user=ada, citation=citation), Alert(user=grace, citation=citation)])
    await session.commit()

    # Relationships are loaded up front in async code, never lazily.
    unseen = (
        await session.exec(
            select(Alert)
            .where(Alert.user_id == "ada", Alert.seen == False)  # noqa: E712
            .options(
                selectinload(Alert.citation).selectinload(Citation.citing_work),
                selectinload(Alert.citation).selectinload(Citation.work),
            )
        )
    ).all()
    assert len(unseen) == 1
    assert unseen[0].citation.citing_work.title == "A Paper That Cites It"
    assert unseen[0].citation.work.key == "10.1234/abc"
    assert unseen[0].emailed is False
    assert (await session.exec(select(CitingWork))).one().affiliations == ["MIT"]


@needs_db
async def test_the_same_citation_cannot_be_recorded_twice(session) -> None:
    paper, citing = _paper(), _citing()
    session.add(Citation(work=paper, citing_work=citing))
    await session.commit()

    session.add(Citation(work_id=paper.id, citing_work_id=citing.id))
    with pytest.raises(IntegrityError):
        await session.commit()


@needs_db
async def test_an_identity_key_belongs_to_one_citing_paper(session) -> None:
    a, b = _citing("10.1/a"), _citing("10.1/b")
    a.keys = [CitingWorkKey(key="id:w42")]
    session.add_all([a, b])
    await session.commit()
    session.expunge_all()  # so the clash is caught by Postgres, not the session

    session.add(CitingWorkKey(key="id:w42", citing_work_id=b.id))
    with pytest.raises(IntegrityError):
        await session.commit()


@needs_db
async def test_two_papers_cannot_share_a_doi(session) -> None:
    session.add(_paper("10.1/a"))
    await session.commit()
    session.add(Work(key="W123", doi="10.1/a", title="Duplicate"))
    with pytest.raises(IntegrityError):
        await session.commit()


@needs_db
async def test_deleting_a_user_removes_their_tracking_and_alerts_only(session) -> None:
    paper, citing = _paper(), _citing()
    ada, grace = User(id="ada", email="a@x.org"), User(id="grace", email="g@x.org")
    citation = Citation(work=paper, citing_work=citing)
    session.add_all([
        UserWork(user=ada, work=paper),
        UserWork(user=grace, work=paper),
        Alert(user=ada, citation=citation),
        Alert(user=grace, citation=citation),
    ])
    await session.commit()

    # passive_deletes: Postgres's ON DELETE CASCADE removes ada's rows, so
    # nothing has to be loaded first.
    await session.delete(ada)
    await session.commit()
    session.expunge_all()

    assert (await session.exec(select(User.id))).all() == ["grace"]
    assert [a.user_id for a in (await session.exec(select(Alert))).all()] == ["grace"]
    assert [t.user_id for t in (await session.exec(select(UserWork))).all()] == ["grace"]
    # The paper and its citation stay for the people still tracking it.
    assert (await session.exec(select(Work))).one().key == "10.1234/abc"
    assert (await session.exec(select(Citation))).one().id == citation.id


@needs_db
async def test_rows_written_with_plain_sql_get_the_defaults(session) -> None:
    await session.exec(text("INSERT INTO users (id) VALUES ('raw')"))
    await session.commit()

    user = await session.get(User, "raw")
    assert user.email == ""
    assert user.notify_enabled is True and user.notify_new_publications is True
    assert user.name_aliases == [] and user.additional_linked_authors == []
    assert user.created_at is not None and user.created_at.tzinfo is not None

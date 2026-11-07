"""
The Postgres schema: migrations, constraints and ORM relationships.

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
from sqlmodel import Session, select

from app.db import DatabaseNotConfigured, make_engine, sqlalchemy_url
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
def engine():
    host = urlsplit(sqlalchemy_url(TEST_URL)).hostname
    if host not in _LOCAL_HOSTS:
        pytest.fail(f"TEST_DATABASE_URL must point at a local throwaway database, not {host!r}")
    cfg = _alembic_config()
    # Down and up again, so the downgrade is exercised too.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = make_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
    with engine.begin() as conn:
        tables = ", ".join(
            t for t in inspect(conn).get_table_names() if t != "alembic_version"
        )
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


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


def test_session_needs_a_database_url(monkeypatch) -> None:
    from app import db
    from app.config import Settings

    monkeypatch.setattr(db, "get_settings", lambda: Settings(database_url=""))
    db.get_engine.cache_clear()
    with pytest.raises(DatabaseNotConfigured):
        next(db.get_session())
    db.get_engine.cache_clear()


# --- Against Postgres --------------------------------------------------------


@needs_db
def test_migrations_match_the_models(engine) -> None:
    # Raises if a table in app/models/ changed without a new migration.
    command.check(_alembic_config())


@needs_db
def test_a_paper_is_stored_once_however_many_people_track_it(session) -> None:
    paper = _paper()
    for uid in ("ada", "grace", "alan"):
        session.add(User(id=uid, email=f"{uid}@uni.edu"))
        session.add(UserWork(user_id=uid, work=paper))
    session.commit()

    assert session.exec(select(Work)).all() == [paper]
    assert sorted(t.user_id for t in paper.trackers) == ["ada", "alan", "grace"]


@needs_db
def test_a_new_citation_becomes_one_alert_per_tracker(session) -> None:
    paper = _paper()
    ada, grace = User(id="ada", email="ada@uni.edu"), User(id="grace", email="g@uni.edu")
    session.add_all([UserWork(user=ada, work=paper), UserWork(user=grace, work=paper)])
    citing = _citing(authors=["Barbara Liskov"], affiliations=["MIT"])
    citing.keys = [CitingWorkKey(key="doi:10.9999/cites"), CitingWorkKey(key="id:w42")]
    citation = Citation(work=paper, citing_work=citing)
    session.add_all([Alert(user=ada, citation=citation), Alert(user=grace, citation=citation)])
    session.commit()

    unseen = session.exec(
        select(Alert).where(Alert.user_id == "ada", Alert.seen == False)  # noqa: E712
    ).all()
    assert len(unseen) == 1
    assert unseen[0].citation.citing_work.title == "A Paper That Cites It"
    assert unseen[0].citation.work.key == "10.1234/abc"
    assert unseen[0].emailed is False
    assert session.exec(select(CitingWork)).one().affiliations == ["MIT"]


@needs_db
def test_the_same_citation_cannot_be_recorded_twice(session) -> None:
    paper, citing = _paper(), _citing()
    session.add(Citation(work=paper, citing_work=citing))
    session.commit()

    session.add(Citation(work_id=paper.id, citing_work_id=citing.id))
    with pytest.raises(IntegrityError):
        session.commit()


@needs_db
def test_an_identity_key_belongs_to_one_citing_paper(session) -> None:
    a, b = _citing("10.1/a"), _citing("10.1/b")
    a.keys = [CitingWorkKey(key="id:w42")]
    session.add_all([a, b])
    session.commit()

    session.add(CitingWorkKey(key="id:w42", citing_work_id=b.id))
    with pytest.raises(IntegrityError):
        session.commit()


@needs_db
def test_two_papers_cannot_share_a_doi(session) -> None:
    session.add(_paper("10.1/a"))
    session.commit()
    session.add(Work(key="W123", doi="10.1/a", title="Duplicate"))
    with pytest.raises(IntegrityError):
        session.commit()


@needs_db
def test_deleting_a_user_removes_their_tracking_and_alerts_only(session) -> None:
    paper, citing = _paper(), _citing()
    ada, grace = User(id="ada", email="a@x.org"), User(id="grace", email="g@x.org")
    citation = Citation(work=paper, citing_work=citing)
    session.add_all([
        UserWork(user=ada, work=paper),
        UserWork(user=grace, work=paper),
        Alert(user=ada, citation=citation),
        Alert(user=grace, citation=citation),
    ])
    session.commit()

    session.delete(ada)
    session.commit()

    assert session.exec(select(User.id)).all() == ["grace"]
    assert [a.user_id for a in session.exec(select(Alert)).all()] == ["grace"]
    # The paper and its citation stay for the people still tracking it.
    assert session.exec(select(Work)).one() is paper
    assert session.exec(select(Citation)).one() is citation


@needs_db
def test_rows_written_with_plain_sql_get_the_defaults(session) -> None:
    session.connection().execute(text("INSERT INTO users (id) VALUES ('raw')"))
    session.commit()

    user = session.get(User, "raw")
    assert user.email == ""
    assert user.notify_enabled is True and user.notify_new_publications is True
    assert user.name_aliases == [] and user.additional_linked_authors == []
    assert user.created_at is not None and user.created_at.tzinfo is not None

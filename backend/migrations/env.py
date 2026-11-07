"""
Alembic environment, on the same async engine as the app. Migrations run
against DATABASE_URL_UNPOOLED, Neon's
direct connection, when it is set: schema changes take locks and run long
statements, which the pooler is not meant for. Without it they use
DATABASE_URL. A URL passed in the Alembic config (as the tests do) wins.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers the tables on SQLModel.metadata)
from app.config import get_settings
from app.core.db import make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    settings = get_settings()
    url = settings.database_url_unpooled or settings.database_url
    if not url:
        raise SystemExit(
            "Set DATABASE_URL_UNPOOLED or DATABASE_URL (backend/.env) to run migrations."
        )
    return url


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    from app.core.db import sqlalchemy_url

    _configure(url=sqlalchemy_url(_database_url()), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_async() -> None:
    engine = make_engine(_database_url())
    async with engine.connect() as connection:
        # Alembic's migration code is synchronous; run_sync hands it the
        # async connection's sync facade.
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_migrations_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

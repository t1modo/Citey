"""
Postgres tables, as SQLModel models (SQLAlchemy 2.1 ORM tables that are also
Pydantic models).

A paper is one row in
``works`` however many people track it, a citing paper is one row in
``citing_works``, and "A cites B" is one row in ``citations``. What differs
per user (who tracks what, and which alerts they have seen or been emailed)
lives in ``user_works`` and ``alerts``.

    users ─< user_works >─ works ─< citations >─ citing_works ─< citing_work_keys
      └──────────< alerts >───────────┘

The API's request and response shapes are in ``app.schemas``; these are the
storage layer only. Shared pieces (the Base class, constraint names, column
helpers) are in ``base.py``. Change a table, then generate a migration:

    uv run alembic revision --autogenerate -m "what changed"
"""

from app.models.base import Base, metadata
from app.models.user import User
from app.models.work import UserWork, Work
from app.models.citation import Citation, CitingWork, CitingWorkKey
from app.models.alert import Alert
from app.models.support import SupportLimit

__all__ = [
    "Alert",
    "Base",
    "Citation",
    "CitingWork",
    "CitingWorkKey",
    "SupportLimit",
    "User",
    "UserWork",
    "Work",
    "metadata",
]

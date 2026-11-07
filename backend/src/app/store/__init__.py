"""
Database access, and nothing else: one store per area, each over the
request's AsyncSession (app.core.db.get_session).

    base.py       BaseStore: the session, get / add / delete / refresh
    user.py       UserStore      users
    work.py       WorkStore      works, user_works (who tracks what)
    citation.py   CitationStore  citing_works, citing_work_keys, citations
    alert.py      AlertStore     alerts (each user's citations)
    limit.py      LimitStore     support_limits

Stores return model rows and never commit. Services (app.services) use
them: they decide what should happen, convert rows to the API's shapes,
and commit once per request.

    work_store = WorkStore(session)
    work = await work_store.get_by_key("10.1__x")
"""

from app.store.alert import AlertRow, AlertStore
from app.store.base import BaseStore
from app.store.citation import CitationStore
from app.store.limit import LimitStore
from app.store.user import UserStore
from app.store.work import WorkStore

__all__ = [
    "AlertRow",
    "AlertStore",
    "BaseStore",
    "CitationStore",
    "LimitStore",
    "UserStore",
    "WorkStore",
]

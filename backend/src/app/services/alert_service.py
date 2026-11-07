"""
Each user's citation alerts, as the API shows them. The database work is in
AlertStore; nothing here commits.
"""

from datetime import datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from app.schemas import Notification
from app.services import convert
from app.store import AlertStore


async def notifications(
    session: AsyncSession, uid: str, *, since: datetime | None = None, limit: int | None = None
) -> list[Notification]:
    """The user's alerts, newest first."""
    rows = await AlertStore(session).for_user(uid, since=since, limit=limit)
    return [convert.notification(*row) for row in rows]


async def notification(session: AsyncSession, uid: str, alert_id: int) -> Notification | None:
    row = await AlertStore(session).one_for_user(uid, alert_id)
    return convert.notification(*row) if row else None


async def pending_email(session: AsyncSession, uid: str, since: datetime) -> list[Notification]:
    """Alerts from *since* on whose email has not gone out, oldest first."""
    rows = await AlertStore(session).pending_email(uid, since)
    return [convert.notification(*row) for row in rows]

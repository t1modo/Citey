"""Contact form rate limits: the ``support_limits`` table."""

from datetime import datetime, timedelta

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import SupportLimit


async def take(session: AsyncSession, key: str, limit: int, window_seconds: int, now: datetime) -> bool:
    """
    Count one use of *key*; False when it is already at *limit* within the
    window. One atomic statement, so two requests at once can't both slip
    under the limit.
    """
    expired = SupportLimit.window_start <= now - timedelta(seconds=window_seconds)
    stmt = insert(SupportLimit).values(key=key, window_start=now, count=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "window_start": case((expired, now), else_=SupportLimit.window_start),
            "count": case((expired, 1), else_=SupportLimit.count + 1),
        },
    )
    used = (await session.exec(stmt.returning(SupportLimit.count))).scalar_one()
    return used <= limit

"""Each user's citations: the ``alerts`` table."""

from datetime import datetime

from sqlalchemy import case, delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Alert, Citation, CitingWork, Work
from app.schemas import Notification
from app.store import convert


def _with_details():
    return (
        select(Alert, Citation, CitingWork, Work)
        .join(Citation, Citation.id == Alert.citation_id)
        .join(CitingWork, CitingWork.id == Citation.citing_work_id)
        .join(Work, Work.id == Citation.work_id)
    )


async def for_user(
    session: AsyncSession, uid: str, *, since: datetime | None = None, limit: int | None = None
) -> list[Notification]:
    """The user's alerts, newest first; only those created at or after *since*."""
    query = _with_details().where(Alert.user_id == uid)
    if since is not None:
        query = query.where(Alert.created_at >= since)
    query = query.order_by(Alert.created_at.desc(), Alert.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return [convert.notification(*row) for row in (await session.exec(query)).all()]


async def get(session: AsyncSession, uid: str, alert_id: int) -> Notification | None:
    row = (await session.exec(_with_details().where(Alert.user_id == uid, Alert.id == alert_id))).first()
    return convert.notification(*row) if row else None


async def counts_by_work(session: AsyncSession, uid: str, since: datetime) -> dict[str, tuple[int, int]]:
    """{paper key: (alerts, alerts created at or after *since*)} for the user."""
    rows = await session.exec(
        select(
            Work.key,
            func.count(Alert.id),
            func.count(case((Alert.created_at >= since, Alert.id))),
        )
        .select_from(Alert)
        .join(Citation, Citation.id == Alert.citation_id)
        .join(Work, Work.id == Citation.work_id)
        .where(Alert.user_id == uid)
        .group_by(Work.key)
    )
    return {key: (total, recent) for key, total, recent in rows.all()}


async def mark_seen(session: AsyncSession, uid: str, alert_id: int) -> bool:
    done = await session.exec(
        update(Alert).where(Alert.user_id == uid, Alert.id == alert_id).values(seen=True).returning(Alert.id)
    )
    return done.first() is not None


async def mark_all_seen(session: AsyncSession, uid: str) -> int:
    done = await session.exec(
        update(Alert).where(Alert.user_id == uid, Alert.seen == False).values(seen=True).returning(Alert.id)  # noqa: E712
    )
    return len(done.all())


async def prune(session: AsyncSession, before: datetime, *, uid: str | None = None, dry_run: bool = False) -> int:
    """Delete alerts created before *before* (one user's, or everyone's)."""
    where = [Alert.created_at < before]
    if uid is not None:
        where.append(Alert.user_id == uid)
    if dry_run:
        return (await session.exec(select(func.count()).select_from(Alert).where(*where))).one()
    removed = await session.exec(delete(Alert).where(*where).returning(Alert.id))
    return len(removed.all())


async def pending_email(session: AsyncSession, uid: str, since: datetime) -> list[Notification]:
    """Alerts created at or after *since* whose email has not gone out, oldest first."""
    query = (
        _with_details()
        .where(Alert.user_id == uid, Alert.emailed == False, Alert.created_at >= since)  # noqa: E712
        .order_by(Alert.created_at, Alert.id)
    )
    return [convert.notification(*row) for row in (await session.exec(query)).all()]


async def mark_emailed(session: AsyncSession, alert_ids: list[int]) -> None:
    if alert_ids:
        await session.exec(update(Alert).where(Alert.id.in_(alert_ids)).values(emailed=True))


async def add(
    session: AsyncSession,
    uid: str,
    citation_id: int,
    *,
    created_at: datetime,
    seen: bool = False,
    emailed: bool = False,
) -> bool:
    """One alert; False when the user already had it."""
    done = await session.exec(
        insert(Alert)
        .values(user_id=uid, citation_id=citation_id, created_at=created_at, seen=seen, emailed=emailed)
        .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
        .returning(Alert.id)
    )
    return done.first() is not None


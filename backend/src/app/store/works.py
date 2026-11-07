"""Papers (``works``) and who tracks them (``user_works``)."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, literal, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Alert, Citation, CitingWork, UserWork, Work
from app.store import users

# A user who starts tracking a paper hears about its citations published in
# the last 30 days, as the first check of a new paper always announced them.
RECENT_DAYS = 30

# Metadata a later add may fill in when the shared row lacks it.
_FILLABLE = (
    "doi", "openalex_id", "year", "venue", "work_type",
    "openalex_citation_count", "s2_citation_count",
)


async def get_by_key(session: AsyncSession, key: str) -> Work | None:
    return (await session.exec(select(Work).where(Work.key == key))).first()


async def upsert(session: AsyncSession, key: str, fields: dict[str, Any]) -> Work:
    """
    The shared row for paper *key*, created from *fields* if missing. An
    existing row keeps its metadata and only gains what it lacked, so one
    user's add never overwrites another's.
    """
    values = {"key": key, **{k: v for k, v in fields.items() if k != "key"}}
    stmt = insert(Work).values(**values)
    fill = {c: func.coalesce(getattr(Work, c), stmt.excluded[c]) for c in _FILLABLE if c in values}
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_=fill or {"key": stmt.excluded.key})
    work_id = (await session.exec(stmt.returning(Work.id))).scalar_one()
    work = await session.get(Work, work_id, populate_existing=True)
    assert work is not None
    return work


async def tracks(session: AsyncSession, uid: str, key: str) -> bool:
    found = await session.exec(
        select(UserWork.work_id)
        .join(Work, Work.id == UserWork.work_id)
        .where(UserWork.user_id == uid, Work.key == key)
    )
    return found.first() is not None


async def tracked_keys(session: AsyncSession, uid: str) -> set[str]:
    rows = await session.exec(
        select(Work.key).join(UserWork, UserWork.work_id == Work.id).where(UserWork.user_id == uid)
    )
    return {k.lower() for k in rows.all()}


async def tracked(session: AsyncSession, uid: str) -> list[tuple[Work, UserWork]]:
    """The user's papers, with when they started tracking each."""
    rows = await session.exec(
        select(Work, UserWork).join(UserWork, UserWork.work_id == Work.id).where(UserWork.user_id == uid)
    )
    return list(rows.all())


async def track(
    session: AsyncSession,
    uid: str,
    key: str,
    fields: dict[str, Any],
    *,
    now: datetime,
    announce_recent: bool = True,
) -> tuple[Work, bool]:
    """
    Start tracking paper *key* for *uid*. Returns (work, newly_tracked).

    With *announce_recent*, citations already recorded for the paper that
    were published in the last RECENT_DAYS become alerts for this user, as
    the first check of a newly added paper would have announced them.
    Tracking a paper also clears an earlier dismissal of it.
    """
    work = await upsert(session, key, fields)
    added = await session.exec(
        insert(UserWork)
        .values(user_id=uid, work_id=work.id, added_at=now)
        .on_conflict_do_nothing(index_elements=["user_id", "work_id"])
        .returning(UserWork.work_id)
    )
    newly = added.first() is not None
    await users.undismiss_work(session, uid, key)
    if newly and announce_recent:
        await _alert_recent_citations(session, uid, work.id, now)
    return work, newly


async def _alert_recent_citations(session: AsyncSession, uid: str, work_id: int, now: datetime) -> None:
    since = now - timedelta(days=RECENT_DAYS)
    since_date = since.strftime("%Y-%m-%d")
    published_recently = or_(
        and_(CitingWork.publication_date.is_not(None), CitingWork.publication_date != "",
             CitingWork.publication_date >= since_date),
        and_(or_(CitingWork.publication_date.is_(None), CitingWork.publication_date == ""),
             func.coalesce(CitingWork.year, 0) >= since.year),
    )
    recent = (
        select(literal(uid), Citation.id, literal(now))
        .join(CitingWork, CitingWork.id == Citation.citing_work_id)
        .where(Citation.work_id == work_id, published_recently)
    )
    await session.exec(
        insert(Alert)
        .from_select(["user_id", "citation_id", "created_at"], recent)
        .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
    )


async def untrack(session: AsyncSession, uid: str, key: str) -> int | None:
    """
    Stop tracking paper *key*: the user's alerts for it go, and the paper is
    remembered as dismissed. Returns how many alerts were removed, or None
    when the user did not track it. The shared paper row stays.
    """
    work = await get_by_key(session, key)
    if work is None or not await tracks(session, uid, key):
        return None
    removed = await session.exec(
        delete(Alert)
        .where(
            Alert.user_id == uid,
            Alert.citation_id.in_(select(Citation.id).where(Citation.work_id == work.id)),
        )
        .returning(Alert.id)
    )
    count = len(removed.all())
    await session.exec(delete(UserWork).where(UserWork.user_id == uid, UserWork.work_id == work.id))
    await users.dismiss_work(session, uid, key)
    return count

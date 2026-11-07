"""
Citing papers (``citing_works``, ``citing_work_keys``) and who cites what
(``citations``), as the citation check records them.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, literal
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Alert, Citation, CitingWork, CitingWorkKey, UserWork, Work

_CITING_FIELDS = ("doi", "openalex_id", "url", "title", "authors", "affiliations", "year", "publication_date")


async def known_keys(session: AsyncSession, work_id: int) -> set[str]:
    """Identity keys of every citing paper already recorded for the paper,
    plus those reported before Postgres (works.known_citing_keys)."""
    legacy = (await session.exec(select(Work.known_citing_keys).where(Work.id == work_id))).first() or []
    rows = await session.exec(
        select(CitingWorkKey.key)
        .join(Citation, Citation.citing_work_id == CitingWorkKey.citing_work_id)
        .where(Citation.work_id == work_id)
    )
    return set(legacy) | set(rows.all())


async def citing_work_for(session: AsyncSession, key: str, keys: set[str], fields: dict[str, Any]) -> int:
    """
    The ID of the citing paper known by any of *keys*, created as *key* with
    *fields* if none is. Every key is then recorded for it, so the same paper
    reported later by another source, or under another version, is found.
    """
    all_keys = set(keys)
    existing = None
    if all_keys:
        existing = (
            await session.exec(
                select(CitingWorkKey.citing_work_id).where(CitingWorkKey.key.in_(sorted(all_keys))).limit(1)
            )
        ).first()
    if existing is None:
        values = {"key": key, **{f: fields[f] for f in _CITING_FIELDS if fields.get(f) is not None}}
        values.setdefault("title", "Untitled")
        stmt = insert(CitingWork).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"key": stmt.excluded.key})
        existing = (await session.exec(stmt.returning(CitingWork.id))).scalar_one()
    if all_keys:
        await session.exec(
            insert(CitingWorkKey)
            .values([{"key": k, "citing_work_id": existing} for k in sorted(all_keys)])
            .on_conflict_do_nothing(index_elements=["key"])
        )
    return existing


async def record(
    session: AsyncSession,
    work_id: int,
    key: str,
    keys: set[str],
    fields: dict[str, Any],
    *,
    found_at: datetime,
) -> tuple[int, bool]:
    """
    Record that the citing paper (*key*, *keys*, *fields*) cites paper
    *work_id*. Returns (citation ID, newly recorded).
    """
    citing_id = await citing_work_for(session, key, keys, fields)
    created = await session.exec(
        insert(Citation)
        .values(work_id=work_id, citing_work_id=citing_id, found_at=found_at)
        .on_conflict_do_nothing(index_elements=["work_id", "citing_work_id"])
        .returning(Citation.id)
    )
    new_id = created.first()
    if new_id is not None:
        return new_id[0], True
    existing = await session.exec(
        select(Citation.id).where(Citation.work_id == work_id, Citation.citing_work_id == citing_id)
    )
    return existing.one(), False


async def alert_trackers(session: AsyncSession, citation_id: int, *, created_at: datetime) -> list[str]:
    """An alert for every user tracking the cited paper. Returns who got a new one."""
    trackers = (
        select(
            UserWork.user_id,
            literal(citation_id, BigInteger),
            literal(created_at, DateTime(timezone=True)),
        )
        .join(Citation, Citation.work_id == UserWork.work_id)
        .where(Citation.id == citation_id)
    )
    added = await session.exec(
        insert(Alert)
        .from_select(["user_id", "citation_id", "created_at"], trackers)
        .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
        .returning(Alert.user_id)
    )
    return list(added.scalars().all())

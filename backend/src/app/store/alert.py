"""AlertStore: each user's citations, the ``alerts`` table."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, case, delete, func, literal, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.models import Alert, Citation, CitingWork, UserWork, Work
from app.store.base import BaseStore

# An alert with what it points at: (Alert, Citation, CitingWork, Work).
AlertRow = tuple[Alert, Citation, CitingWork, Work]


def _with_details():
    return (
        select(Alert, Citation, CitingWork, Work)
        .join(Citation, Citation.id == Alert.citation_id)
        .join(CitingWork, CitingWork.id == Citation.citing_work_id)
        .join(Work, Work.id == Citation.work_id)
    )


class AlertStore(BaseStore[Alert]):
    model = Alert

    async def for_user(self, uid: str, *, since: datetime | None = None, limit: int | None = None) -> list[AlertRow]:
        """The user's alerts, newest first; only those created at or after *since*."""
        query = _with_details().where(Alert.user_id == uid)
        if since is not None:
            query = query.where(Alert.created_at >= since)
        query = query.order_by(Alert.created_at.desc(), Alert.id.desc())
        if limit is not None:
            query = query.limit(limit)
        return list((await self.session.exec(query)).all())

    async def one_for_user(self, uid: str, alert_id: int) -> AlertRow | None:
        return (await self.session.exec(_with_details().where(Alert.user_id == uid, Alert.id == alert_id))).first()

    async def counts_by_work(self, uid: str, since: datetime) -> dict[str, tuple[int, int]]:
        """{paper key: (alerts, alerts created at or after *since*)} for the user."""
        rows = await self.session.exec(
            select(Work.key, func.count(Alert.id), func.count(case((Alert.created_at >= since, Alert.id))))
            .select_from(Alert)
            .join(Citation, Citation.id == Alert.citation_id)
            .join(Work, Work.id == Citation.work_id)
            .where(Alert.user_id == uid)
            .group_by(Work.key)
        )
        return {key: (total, recent) for key, total, recent in rows.all()}

    async def pending_email(self, uid: str, since: datetime) -> list[AlertRow]:
        """Alerts created at or after *since* whose email has not gone out, oldest first."""
        query = (
            _with_details()
            .where(Alert.user_id == uid, Alert.emailed == False, Alert.created_at >= since)  # noqa: E712
            .order_by(Alert.created_at, Alert.id)
        )
        return list((await self.session.exec(query)).all())

    async def add(
        self, uid: str, citation_id: int, *, created_at: datetime, seen: bool = False, emailed: bool = False
    ) -> bool:
        """One alert; False when the user already had it."""
        done = await self.session.exec(
            insert(Alert)
            .values(user_id=uid, citation_id=citation_id, created_at=created_at, seen=seen, emailed=emailed)
            .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
            .returning(Alert.id)
        )
        return done.first() is not None

    async def add_many(self, uid: str, citation_ids: list[int], *, created_at: datetime) -> int:
        """Alerts for *uid* on each citation; returns how many were new."""
        if not citation_ids:
            return 0
        done = await self.session.exec(
            insert(Alert)
            .values([{"user_id": uid, "citation_id": c, "created_at": created_at} for c in citation_ids])
            .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
            .returning(Alert.id)
        )
        return len(done.all())

    async def add_for_trackers(self, citation_id: int, *, created_at: datetime) -> list[str]:
        """An alert for every user tracking the cited paper. Returns who got a new one."""
        trackers = (
            select(UserWork.user_id, literal(citation_id, BigInteger), literal(created_at, DateTime(timezone=True)))
            .join(Citation, Citation.work_id == UserWork.work_id)
            .where(Citation.id == citation_id)
        )
        added = await self.session.exec(
            insert(Alert)
            .from_select(["user_id", "citation_id", "created_at"], trackers)
            .on_conflict_do_nothing(index_elements=["user_id", "citation_id"])
            .returning(Alert.user_id)
        )
        return list(added.scalars().all())

    async def mark_seen(self, uid: str, alert_id: int) -> bool:
        done = await self.session.exec(
            update(Alert).where(Alert.user_id == uid, Alert.id == alert_id).values(seen=True).returning(Alert.id)
        )
        return done.first() is not None

    async def mark_all_seen(self, uid: str) -> int:
        done = await self.session.exec(
            update(Alert).where(Alert.user_id == uid, Alert.seen == False).values(seen=True).returning(Alert.id)  # noqa: E712
        )
        return len(done.all())

    async def mark_emailed(self, alert_ids: list[int]) -> None:
        if alert_ids:
            await self.session.exec(update(Alert).where(Alert.id.in_(alert_ids)).values(emailed=True))

    async def prune(self, before: datetime, *, uid: str | None = None, dry_run: bool = False) -> int:
        """Delete alerts created before *before* (one user's, or everyone's)."""
        where = [Alert.created_at < before]
        if uid is not None:
            where.append(Alert.user_id == uid)
        if dry_run:
            return (await self.session.exec(select(func.count()).select_from(Alert).where(*where))).one()
        removed = await self.session.exec(delete(Alert).where(*where).returning(Alert.id))
        return len(removed.all())

    async def delete_for_user(self, uid: str, *, work_id: int | None = None) -> int:
        """Delete the user's alerts (only those for *work_id*, when given)."""
        where = [Alert.user_id == uid]
        if work_id is not None:
            where.append(Alert.citation_id.in_(select(Citation.id).where(Citation.work_id == work_id)))
        removed = await self.session.exec(delete(Alert).where(*where).returning(Alert.id))
        return len(removed.all())

"""WorkStore: papers (``works``) and who tracks them (``user_works``)."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, exists, func, literal_column, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.models import Alert, Citation, CitingWork, UserWork, Work
from app.store.base import BaseStore

# Metadata a later add may fill in when the shared row lacks it.
_FILLABLE = (
    "doi", "openalex_id", "year", "venue", "work_type",
    "openalex_citation_count", "s2_citation_count",
)


class WorkStore(BaseStore[Work]):
    model = Work

    async def get_by_key(self, key: str) -> Work | None:
        return (await self.session.exec(select(Work).where(Work.key == key))).first()

    async def upsert(self, key: str, fields: dict[str, Any]) -> Work:
        """
        The shared row for paper *key*, created from *fields* if missing. An
        existing row keeps its metadata and only gains what it lacked.
        """
        values = {"key": key, **{k: v for k, v in fields.items() if k != "key"}}
        stmt = insert(Work).values(**values)
        fill = {c: func.coalesce(getattr(Work, c), stmt.excluded[c]) for c in _FILLABLE if c in values}
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_=fill or {"key": stmt.excluded.key})
        work_id = (await self.session.exec(stmt.returning(Work.id))).scalar_one()
        work = await self.session.get(Work, work_id, populate_existing=True)
        assert work is not None
        return work

    async def merge(self, values: dict[str, Any]) -> int:
        """
        Insert a paper, or merge *values* into the existing row: metadata it
        lacks is filled in, counts, last check and citation window take the
        larger value, and known_citing_keys become the union. Used when
        several users' copies of one paper are combined. Returns the row ID.
        """
        stmt = insert(Work).values(**values)
        ex = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={
                "doi": func.coalesce(Work.doi, ex.doi),
                "openalex_id": func.coalesce(Work.openalex_id, ex.openalex_id),
                "venue": func.coalesce(Work.venue, ex.venue),
                "work_type": func.coalesce(Work.work_type, ex.work_type),
                "openalex_citation_count": func.greatest(Work.openalex_citation_count, ex.openalex_citation_count),
                "s2_citation_count": func.greatest(Work.s2_citation_count, ex.s2_citation_count),
                "last_checked_at": func.greatest(Work.last_checked_at, ex.last_checked_at),
                "citation_window": func.greatest(Work.citation_window, ex.citation_window),
                # Both copies' keys, each once.
                "known_citing_keys": literal_column(
                    "ARRAY(SELECT DISTINCT k FROM unnest(works.known_citing_keys"
                    " || excluded.known_citing_keys) AS k ORDER BY k)"
                ),
            },
        )
        return (await self.session.exec(stmt.returning(Work.id))).scalar_one()

    async def update_fields(self, work_id: int, **fields: Any) -> None:
        """Set columns on the paper's row (column names as in app.models.Work)."""
        if fields:
            await self.session.exec(update(Work).where(Work.id == work_id).values(**fields))

    async def add_tracker(self, uid: str, work_id: int, added_at: datetime) -> bool:
        """*uid* tracks *work_id* from *added_at*. False when they already did."""
        added = await self.session.exec(
            insert(UserWork)
            .values(user_id=uid, work_id=work_id, added_at=added_at)
            .on_conflict_do_nothing(index_elements=["user_id", "work_id"])
            .returning(UserWork.work_id)
        )
        return added.first() is not None

    async def remove_tracker(self, uid: str, work_id: int) -> None:
        await self.session.exec(delete(UserWork).where(UserWork.user_id == uid, UserWork.work_id == work_id))

    async def remove_all_trackers(self, uid: str) -> None:
        await self.session.exec(delete(UserWork).where(UserWork.user_id == uid))

    async def tracks(self, uid: str, key: str) -> bool:
        found = await self.session.exec(
            select(UserWork.work_id)
            .join(Work, Work.id == UserWork.work_id)
            .where(UserWork.user_id == uid, Work.key == key)
        )
        return found.first() is not None

    async def tracked_keys(self, uid: str) -> set[str]:
        rows = await self.session.exec(
            select(Work.key).join(UserWork, UserWork.work_id == Work.id).where(UserWork.user_id == uid)
        )
        return {k.lower() for k in rows.all()}

    async def tracked(self, uid: str) -> list[tuple[Work, UserWork]]:
        """The user's papers, with when they started tracking each."""
        rows = await self.session.exec(
            select(Work, UserWork).join(UserWork, UserWork.work_id == Work.id).where(UserWork.user_id == uid)
        )
        return list(rows.all())

    async def prune_untracked(self, before: datetime, *, dry_run: bool = False) -> dict[str, int]:
        """
        Delete papers nobody tracks any more, and citing papers no citation
        points at, created before *before*.

        A paper goes when no user_works row and no alert refers to it; its
        citations go with it (ON DELETE CASCADE). A citing paper goes when no
        citation is left for it; its identity keys go with it. Rows newer than
        *before* are kept, so a paper being added while this runs is never
        removed from under the request adding it.
        """
        untracked = [
            Work.created_at < before,
            ~exists().where(UserWork.work_id == Work.id),
            ~exists().where(Alert.citation_id == Citation.id, Citation.work_id == Work.id),
        ]
        if dry_run:
            works = (await self.session.exec(select(func.count()).select_from(Work).where(*untracked))).one()
            citing_ids = select(CitingWork.id).where(
                CitingWork.created_at < before,
                ~exists().where(
                    Citation.citing_work_id == CitingWork.id,
                    Citation.work_id.not_in(select(Work.id).where(*untracked)),
                ),
            )
            citing = (await self.session.exec(select(func.count()).select_from(citing_ids.subquery()))).one()
            return {"works": works, "citing_works": citing}

        works = len((await self.session.exec(delete(Work).where(*untracked).returning(Work.id))).all())
        orphaned = [CitingWork.created_at < before, ~exists().where(Citation.citing_work_id == CitingWork.id)]
        citing = len((await self.session.exec(delete(CitingWork).where(*orphaned).returning(CitingWork.id))).all())
        return {"works": works, "citing_works": citing}

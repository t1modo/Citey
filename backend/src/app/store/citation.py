"""
CitationStore: citing papers (``citing_works``, ``citing_work_keys``) and who
cites what (``citations``).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.models import Citation, CitingWork, CitingWorkKey, Work
from app.store.base import BaseStore

_CITING_FIELDS = ("doi", "openalex_id", "url", "title", "authors", "affiliations", "year", "publication_date")


class CitationStore(BaseStore[Citation]):
    model = Citation

    async def known_keys(self, work_id: int) -> set[str]:
        """Identity keys of every citing paper recorded for the paper, plus
        those reported before Postgres (works.known_citing_keys)."""
        legacy = (await self.session.exec(select(Work.known_citing_keys).where(Work.id == work_id))).first() or []
        rows = await self.session.exec(
            select(CitingWorkKey.key)
            .join(Citation, Citation.citing_work_id == CitingWorkKey.citing_work_id)
            .where(Citation.work_id == work_id)
        )
        return set(legacy) | set(rows.all())

    async def citing_work_for(self, key: str, keys: set[str], fields: dict[str, Any]) -> int:
        """
        The ID of the citing paper known by any of *keys*, created as *key*
        with *fields* if none is. Every key is then recorded for it, so the
        same paper reported later by another source is found.
        """
        existing = None
        if keys:
            existing = (
                await self.session.exec(
                    select(CitingWorkKey.citing_work_id).where(CitingWorkKey.key.in_(sorted(keys))).limit(1)
                )
            ).first()
        if existing is None:
            values = {"key": key, **{f: fields[f] for f in _CITING_FIELDS if fields.get(f) is not None}}
            values.setdefault("title", "Untitled")
            stmt = insert(CitingWork).values(**values)
            stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"key": stmt.excluded.key})
            existing = (await self.session.exec(stmt.returning(CitingWork.id))).scalar_one()
        if keys:
            await self.session.exec(
                insert(CitingWorkKey)
                .values([{"key": k, "citing_work_id": existing} for k in sorted(keys)])
                .on_conflict_do_nothing(index_elements=["key"])
            )
        return existing

    async def record(
        self,
        work_id: int,
        key: str,
        keys: set[str],
        fields: dict[str, Any],
        *,
        found_at: datetime,
    ) -> tuple[int, bool]:
        """Record that the citing paper cites *work_id*. Returns (citation ID, newly recorded)."""
        citing_id = await self.citing_work_for(key, keys, fields)
        created = await self.session.exec(
            insert(Citation)
            .values(work_id=work_id, citing_work_id=citing_id, found_at=found_at)
            .on_conflict_do_nothing(index_elements=["work_id", "citing_work_id"])
            .returning(Citation.id)
        )
        new_id = created.scalars().first()
        if new_id is not None:
            return new_id, True
        existing = await self.session.exec(
            select(Citation.id).where(Citation.work_id == work_id, Citation.citing_work_id == citing_id)
        )
        return existing.one(), False

    async def published_since(self, work_id: int, since: datetime) -> list[int]:
        """IDs of the paper's citations by papers published on or after *since*
        (undated papers by year)."""
        since_date = since.strftime("%Y-%m-%d")
        dated = and_(CitingWork.publication_date.is_not(None), CitingWork.publication_date != "")
        recent = or_(
            and_(dated, CitingWork.publication_date >= since_date),
            and_(~dated, func.coalesce(CitingWork.year, 0) >= since.year),
        )
        rows = await self.session.exec(
            select(Citation.id)
            .join(CitingWork, CitingWork.id == Citation.citing_work_id)
            .where(Citation.work_id == work_id, recent)
        )
        return list(rows.all())

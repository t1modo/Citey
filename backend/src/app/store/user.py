"""UserStore: the ``users`` table."""

from typing import Any

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.models import User
from app.store.base import BaseStore


class UserStore(BaseStore[User]):
    model = User

    async def create(self, uid: str, email: str = "", **fields: Any) -> User:
        """The user's row, created if missing. An existing row is left as it is."""
        await self.session.exec(
            insert(User)
            .values(**{"id": uid, "email": email, "notification_email": email or None, **fields})
            .on_conflict_do_nothing(index_elements=["id"])
        )
        user = await self.session.get(User, uid, populate_existing=True)
        assert user is not None
        return user

    async def upsert(self, uid: str, values: dict[str, Any], *, created_at: Any = None) -> None:
        """Insert the user, or overwrite these columns if they exist."""
        stmt = insert(User).values(id=uid, **values, **({"created_at": created_at} if created_at else {}))
        await self.session.exec(stmt.on_conflict_do_update(index_elements=["id"], set_=values))

    async def update_fields(self, uid: str, **fields: Any) -> None:
        """Set columns on the user's row (column names as in app.models.User)."""
        if fields:
            await self.session.exec(update(User).where(User.id == uid).values(**fields))

    async def delete_by_id(self, uid: str) -> None:
        """Delete the account. Its tracking and alerts go with it (ON DELETE
        CASCADE). Papers it alone tracked are removed by the nightly
        prune_untracked_papers."""
        await self.session.exec(delete(User).where(User.id == uid))

    async def ids_after(self, cursor: str | None = None) -> list[str]:
        """Every user ID in order, after *cursor* when given (for batched jobs)."""
        query = select(User.id).order_by(User.id)
        if cursor is not None:
            query = query.where(User.id > cursor)
        return list((await self.session.exec(query)).all())

    async def dismiss_work(self, uid: str, key: str) -> None:
        """Add *key* to the user's dismissed papers, once."""
        key = key.lower()
        await self.session.exec(
            update(User)
            .where(User.id == uid, func.array_position(User.dismissed_work_keys, key).is_(None))
            .values(dismissed_work_keys=func.array_append(User.dismissed_work_keys, key))
        )

    async def undismiss_work(self, uid: str, key: str) -> None:
        await self.session.exec(
            update(User)
            .where(User.id == uid)
            .values(dismissed_work_keys=func.array_remove(User.dismissed_work_keys, key.lower()))
        )

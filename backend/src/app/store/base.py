"""BaseStore: what every store shares."""

from typing import Any, Generic, TypeVar

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

ModelT = TypeVar("ModelT", bound=SQLModel)


class BaseStore(Generic[ModelT]):
    """
    Database access for one table (``model``) and the queries around it.

    A store holds the request's session. It reads and writes, flushes so
    later statements see its changes, and never commits: the service or
    router commits once its whole change is made, so a request saves
    everything or nothing. Stores return model rows; turning them into API
    shapes, and deciding what should happen, is the services' job.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: Any) -> ModelT | None:
        """The row with this primary key, or None."""
        return await self.session.get(self.model, id)

    async def refresh(self, row: ModelT) -> ModelT:
        """Re-read *row* from the database (after a bulk UPDATE changed it)."""
        await self.session.refresh(row)
        return row

    async def add(self, row: ModelT) -> ModelT:
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete(self, row: ModelT) -> None:
        await self.session.delete(row)
        await self.session.flush()

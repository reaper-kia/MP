from dataclasses import replace
from types import TracebackType
from typing import Self
from uuid import UUID

from example_service.applications.context import RequestContext
from example_service.domain.entities import Item


class FakeItemRepository:
    def __init__(self, store: dict[UUID, Item]) -> None:
        self._store = store

    async def add(self, item: Item) -> None:
        self._store[item.id] = replace(item)

    async def save(self, item: Item) -> None:
        self._store[item.id] = replace(item)

    async def delete(self, item_id: UUID) -> None:
        self._store.pop(item_id, None)

    async def get_by_id(self, item_id: UUID) -> Item | None:
        item = self._store.get(item_id)
        return replace(item) if item else None

    async def list_by_owner(self, owner_id: UUID | None, *, limit: int, offset: int) -> list[Item]:
        rows = [i for i in self._store.values() if owner_id is None or i.owner_id == owner_id]
        rows.sort(key=lambda i: i.created_at, reverse=True)
        return rows[offset : offset + limit]


class FakeUnitOfWork:
    def __init__(self, store: dict[UUID, Item]) -> None:
        self.items = FakeItemRepository(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeUserDirectory:
    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None:
        return self.names.get(user_id)

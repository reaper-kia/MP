from dataclasses import replace
from types import TracebackType
from typing import Self
from uuid import UUID

from example_service.application.ports import ItemFilter
from example_service.domain.item import Item
from platform_common.context import RequestContext


class FakeItems:
    def __init__(self, store: dict[UUID, Item]) -> None:
        self._store = store

    async def get(self, item_id: UUID) -> Item | None:
        item = self._store.get(item_id)
        return replace(item) if item else None

    async def add(self, item: Item) -> None:
        self._store[item.id] = replace(item)

    async def update(self, item: Item) -> None:
        self._store[item.id] = replace(item)

    async def delete(self, item_id: UUID) -> None:
        self._store.pop(item_id, None)

    async def list(self, flt: ItemFilter, *, limit: int, offset: int) -> list[Item]:
        rows = [
            i
            for i in self._store.values()
            if (flt.owner_id is None or i.owner_id == flt.owner_id)
            and (flt.status is None or i.status == flt.status)
        ]
        rows.sort(key=lambda i: i.created_at, reverse=True)
        return rows[offset : offset + limit]


class FakeUnitOfWork:
    """Упрощённо: пишет сразу в общий store (транзакционность тут не проверяем)."""

    def __init__(self, store: dict[UUID, Item]) -> None:
        self.items = FakeItems(store)
        self.committed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class FakeUserDirectory:
    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None:
        return self.names.get(user_id)

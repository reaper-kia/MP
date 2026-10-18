from typing import Protocol
from uuid import UUID

from example_service.domain.entities import Item


class ItemRepository(Protocol):
    async def add(self, item: Item) -> None: ...

    async def save(self, item: Item) -> None: ...

    async def delete(self, item_id: UUID) -> None: ...

    async def get_by_id(self, item_id: UUID) -> Item | None: ...

    async def list_by_owner(self, owner_id: UUID | None, *, limit: int, offset: int) -> list[Item]:
        """owner_id=None — все записи (для админа)."""
        ...

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from example_service.domain.item import Item, ItemStatus
from platform_common.context import RequestContext
from platform_common.db.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class ItemFilter:
    owner_id: UUID | None = None  # None — все (для админа)
    status: ItemStatus | None = None


class ItemRepository(Protocol):
    async def get(self, item_id: UUID) -> Item | None: ...
    async def add(self, item: Item) -> None: ...
    async def update(self, item: Item) -> None: ...
    async def delete(self, item_id: UUID) -> None: ...
    async def list(self, flt: ItemFilter, *, limit: int, offset: int) -> list[Item]: ...


class ExampleUnitOfWork(UnitOfWork, Protocol):
    @property
    def items(self) -> ItemRepository: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> ExampleUnitOfWork: ...


class UserDirectory(Protocol):
    """Данные о пользователях живут в Auth — получаем их по gRPC."""

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None: ...

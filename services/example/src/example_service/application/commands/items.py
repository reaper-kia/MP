"""Команды над Item. Мелкие use case'ы одного агрегата удобно держать в одном файле."""

from dataclasses import dataclass
from uuid import UUID

from example_service.application.dto import ItemView
from example_service.application.ports import ExampleUnitOfWork, UnitOfWorkFactory
from example_service.domain.item import Item, ItemNotFoundError, ItemStatus
from platform_common.context import RequestContext
from platform_common.mediator import Command


async def load_for_change(uow: ExampleUnitOfWork, ctx: RequestContext, item_id: UUID) -> Item:
    item = await uow.items.get(item_id)
    if item is None:
        raise ItemNotFoundError()
    ctx.require_owner_or_admin(item.owner_id)
    return item


@dataclass(frozen=True, slots=True)
class CreateItem(Command[ItemView]):
    ctx: RequestContext
    title: str
    description: str = ""


class CreateItemHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, cmd: CreateItem) -> ItemView:
        owner_id = cmd.ctx.require_user()
        item = Item.create(owner_id, cmd.title, cmd.description)
        async with self._uow_factory() as uow:
            await uow.items.add(item)
            await uow.commit()
        return ItemView.from_item(item)


@dataclass(frozen=True, slots=True)
class UpdateItem(Command[ItemView]):
    ctx: RequestContext
    item_id: UUID
    title: str | None = None
    description: str | None = None
    status: ItemStatus | None = None


class UpdateItemHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, cmd: UpdateItem) -> ItemView:
        async with self._uow_factory() as uow:
            item = await load_for_change(uow, cmd.ctx, cmd.item_id)
            if cmd.title is not None or cmd.description is not None:
                item.edit(title=cmd.title, description=cmd.description)
            if cmd.status is not None:
                item.change_status(cmd.status)
            await uow.items.update(item)
            await uow.commit()
        return ItemView.from_item(item)


@dataclass(frozen=True, slots=True)
class DeleteItem(Command[None]):
    ctx: RequestContext
    item_id: UUID


class DeleteItemHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, cmd: DeleteItem) -> None:
        async with self._uow_factory() as uow:
            await load_for_change(uow, cmd.ctx, cmd.item_id)
            await uow.items.delete(cmd.item_id)
            await uow.commit()

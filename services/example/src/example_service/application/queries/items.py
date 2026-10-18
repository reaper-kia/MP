from dataclasses import dataclass
from uuid import UUID

from example_service.application.dto import ItemPage, ItemView
from example_service.application.ports import ItemFilter, UnitOfWorkFactory, UserDirectory
from example_service.domain.item import ItemNotFoundError, ItemStatus
from platform_common.context import RequestContext
from platform_common.mediator import Query
from platform_common.pagination import Page


@dataclass(frozen=True, slots=True)
class GetItem(Query[ItemView]):
    ctx: RequestContext
    item_id: UUID


class GetItemHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory, users: UserDirectory) -> None:
        self._uow_factory = uow_factory
        self._users = users

    async def handle(self, query: GetItem) -> ItemView:
        async with self._uow_factory() as uow:
            item = await uow.items.get(query.item_id)
        if item is None:
            raise ItemNotFoundError()
        query.ctx.require_owner_or_admin(item.owner_id)
        # Межсервисный вызов — уже после закрытия транзакции.
        owner_name = await self._users.get_name(query.ctx, item.owner_id)
        return ItemView.from_item(item, owner_name)


@dataclass(frozen=True, slots=True)
class ListItems(Query[ItemPage]):
    ctx: RequestContext
    limit: int = 20
    cursor: str = ""
    status: ItemStatus | None = None


class ListItemsHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, query: ListItems) -> ItemPage:
        actor = query.ctx.require_user()
        page = Page.from_request(query.limit, query.cursor)
        flt = ItemFilter(owner_id=None if query.ctx.is_admin else actor, status=query.status)
        async with self._uow_factory() as uow:
            rows = await uow.items.list(flt, limit=page.limit + 1, offset=page.offset)
        return ItemPage(
            items=[ItemView.from_item(i) for i in rows[: page.limit]],
            next_cursor=page.next_cursor(len(rows)),
        )

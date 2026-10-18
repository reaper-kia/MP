from dataclasses import dataclass

from example_service.applications.ports.unit_of_work import UnitOfWorkFactory
from example_service.applications.queries.list_items import ListItemsQuery
from example_service.applications.results.read_models import ItemPage, ItemReadModel

MAX_LIMIT = 100


@dataclass
class ListItemsQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListItemsQuery) -> ItemPage:
        actor_id = query.ctx.require_user()
        limit = min(max(query.limit, 1), MAX_LIMIT)
        owner_id = None if query.ctx.is_admin else actor_id  # админ видит всё

        async with self.uow_factory() as uow:
            # берём на одну запись больше, чтобы понять, есть ли следующая страница
            rows = await uow.items.list_by_owner(owner_id, limit=limit + 1, offset=query.offset)

        return ItemPage(
            items=[ItemReadModel.from_item(i) for i in rows[:limit]],
            has_more=len(rows) > limit,
        )

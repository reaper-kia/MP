from dataclasses import dataclass

from example_service.applications.exceptions import ItemNotFoundError
from example_service.applications.ports.unit_of_work import UnitOfWorkFactory
from example_service.applications.ports.user_directory import UserDirectory
from example_service.applications.queries.get_item import GetItemQuery
from example_service.applications.results.read_models import ItemReadModel


@dataclass
class GetItemQueryHandler:
    uow_factory: UnitOfWorkFactory
    users: UserDirectory

    async def handle(self, query: GetItemQuery) -> ItemReadModel:
        async with self.uow_factory() as uow:
            item = await uow.items.get_by_id(query.item_id)

        if item is None:
            raise ItemNotFoundError("Item not found")
        query.ctx.require_owner_or_admin(item.owner_id)

        # вызов другого сервиса — уже после закрытия транзакции
        owner_name = await self.users.get_name(query.ctx, item.owner_id)
        return ItemReadModel.from_item(item, owner_name)

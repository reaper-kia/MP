from dataclasses import dataclass

from example_service.applications.commands.create_item import CreateItemCommand
from example_service.applications.ports.unit_of_work import UnitOfWorkFactory
from example_service.applications.results.read_models import ItemReadModel
from example_service.domain.entities import Item
from example_service.domain.value_objects import ItemTitle


@dataclass
class CreateItemCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: CreateItemCommand) -> ItemReadModel:
        owner_id = cmd.ctx.require_user()
        item = Item.create(
            owner_id=owner_id, title=ItemTitle(cmd.title), description=cmd.description
        )

        async with self.uow_factory() as uow:
            await uow.items.add(item)
            await uow.commit()

        return ItemReadModel.from_item(item)

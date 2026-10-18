from dataclasses import dataclass

from example_service.applications.commands.update_item import UpdateItemCommand
from example_service.applications.exceptions import ItemNotFoundError
from example_service.applications.ports.unit_of_work import UnitOfWorkFactory
from example_service.applications.results.read_models import ItemReadModel
from example_service.domain.entities import ItemStatus
from example_service.domain.value_objects import ItemTitle


@dataclass
class UpdateItemCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: UpdateItemCommand) -> ItemReadModel:
        async with self.uow_factory() as uow:
            item = await uow.items.get_by_id(cmd.item_id)
            if item is None:
                raise ItemNotFoundError("Item not found")
            cmd.ctx.require_owner_or_admin(item.owner_id)

            if cmd.title is not None or cmd.description is not None:
                title = ItemTitle(cmd.title) if cmd.title is not None else None
                item.edit(title=title, description=cmd.description)
            if cmd.status is not None:
                item.change_status(ItemStatus(cmd.status))

            await uow.items.save(item)
            await uow.commit()

        return ItemReadModel.from_item(item)

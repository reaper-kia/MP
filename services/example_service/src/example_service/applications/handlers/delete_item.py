from dataclasses import dataclass

from example_service.applications.commands.delete_item import DeleteItemCommand
from example_service.applications.exceptions import ItemNotFoundError
from example_service.applications.ports.unit_of_work import UnitOfWorkFactory


@dataclass
class DeleteItemCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: DeleteItemCommand) -> None:
        async with self.uow_factory() as uow:
            item = await uow.items.get_by_id(cmd.item_id)
            if item is None:
                raise ItemNotFoundError("Item not found")
            cmd.ctx.require_owner_or_admin(item.owner_id)

            await uow.items.delete(item.id)
            await uow.commit()

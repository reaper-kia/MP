from dataclasses import dataclass

from platform_common.context import RequestContext
from platform_common.mediator import Command

from {{name}}_service.application.ports import UnitOfWorkFactory
from {{name}}_service.domain.{{entity}} import {{Entity}}


@dataclass(frozen=True, slots=True)
class Create{{Entity}}(Command[{{Entity}}]):
    ctx: RequestContext
    title: str


class Create{{Entity}}Handler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, cmd: Create{{Entity}}) -> {{Entity}}:
        owner_id = cmd.ctx.require_user()
        {{entity}} = {{Entity}}.create(owner_id, cmd.title)
        async with self._uow_factory() as uow:
            await uow.{{entities}}.add({{entity}})
            await uow.commit()
        return {{entity}}

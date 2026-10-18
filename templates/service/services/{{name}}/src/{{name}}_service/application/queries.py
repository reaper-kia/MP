from dataclasses import dataclass
from uuid import UUID

from platform_common.context import RequestContext
from platform_common.mediator import Query
from platform_common.pagination import Page

from {{name}}_service.application.ports import UnitOfWorkFactory
from {{name}}_service.domain.{{entity}} import {{Entity}}, {{Entity}}NotFoundError


@dataclass(frozen=True, slots=True)
class Get{{Entity}}(Query[{{Entity}}]):
    ctx: RequestContext
    {{entity}}_id: UUID


class Get{{Entity}}Handler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, query: Get{{Entity}}) -> {{Entity}}:
        async with self._uow_factory() as uow:
            {{entity}} = await uow.{{entities}}.get(query.{{entity}}_id)
        if {{entity}} is None:
            raise {{Entity}}NotFoundError()
        query.ctx.require_owner_or_admin({{entity}}.owner_id)
        return {{entity}}


@dataclass(frozen=True, slots=True)
class {{Entity}}Page:
    {{entities}}: list[{{Entity}}]
    next_cursor: str


@dataclass(frozen=True, slots=True)
class List{{Entities}}(Query[{{Entity}}Page]):
    ctx: RequestContext
    limit: int = 20
    cursor: str = ""


class List{{Entities}}Handler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, query: List{{Entities}}) -> {{Entity}}Page:
        owner_id = query.ctx.require_user()
        page = Page.from_request(query.limit, query.cursor)
        async with self._uow_factory() as uow:
            rows = await uow.{{entities}}.list_by_owner(owner_id, limit=page.limit + 1, offset=page.offset)
        return {{Entity}}Page(rows[: page.limit], page.next_cursor(len(rows)))

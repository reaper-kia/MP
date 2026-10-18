from typing import Protocol
from uuid import UUID

from platform_common.db.uow import UnitOfWork

from {{name}}_service.domain.{{entity}} import {{Entity}}


class {{Entity}}Repository(Protocol):
    async def get(self, {{entity}}_id: UUID) -> {{Entity}} | None: ...
    async def add(self, {{entity}}: {{Entity}}) -> None: ...
    async def list_by_owner(self, owner_id: UUID, *, limit: int, offset: int) -> list[{{Entity}}]: ...


class {{Name}}UnitOfWork(UnitOfWork, Protocol):
    @property
    def {{entities}}(self) -> {{Entity}}Repository: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> {{Name}}UnitOfWork: ...

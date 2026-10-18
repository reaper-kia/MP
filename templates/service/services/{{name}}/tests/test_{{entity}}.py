from dataclasses import replace
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

import pytest

from platform_common.context import RequestContext
from platform_common.errors import PermissionDeniedError, ValidationError
from {{name}}_service.application.commands import Create{{Entity}}
from {{name}}_service.application.queries import Get{{Entity}}, List{{Entities}}
from {{name}}_service.container import build_mediator
from {{name}}_service.domain.{{entity}} import {{Entity}}


class FakeRepo:
    def __init__(self, store: dict[UUID, {{Entity}}]) -> None:
        self._store = store

    async def get(self, {{entity}}_id: UUID) -> {{Entity}} | None:
        x = self._store.get({{entity}}_id)
        return replace(x) if x else None

    async def add(self, {{entity}}: {{Entity}}) -> None:
        self._store[{{entity}}.id] = replace({{entity}})

    async def list_by_owner(self, owner_id: UUID, *, limit: int, offset: int) -> list[{{Entity}}]:
        rows = sorted(
            (x for x in self._store.values() if x.owner_id == owner_id),
            key=lambda x: x.created_at,
            reverse=True,
        )
        return rows[offset : offset + limit]


class FakeUow:
    def __init__(self, store: dict[UUID, {{Entity}}]) -> None:
        self.{{entities}} = FakeRepo(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def ctx(user: UUID) -> RequestContext:
    return RequestContext("t", actor_user_id=user, actor_role="user")


async def test_create_get_list() -> None:
    store: dict[UUID, {{Entity}}] = {}
    mediator = build_mediator(lambda: FakeUow(store))
    me, other = uuid4(), uuid4()

    created = await mediator.send(Create{{Entity}}(ctx(me), " first "))
    assert created.title == "first"
    assert (await mediator.send(Get{{Entity}}(ctx(me), created.id))).id == created.id
    with pytest.raises(PermissionDeniedError):
        await mediator.send(Get{{Entity}}(ctx(other), created.id))
    with pytest.raises(ValidationError):
        await mediator.send(Create{{Entity}}(ctx(me), ""))

    page = await mediator.send(List{{Entities}}(ctx(me)))
    assert [x.id for x in page.{{entities}}] == [created.id]

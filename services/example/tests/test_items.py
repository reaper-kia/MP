from uuid import UUID, uuid4

import pytest

from example_service.application.commands.items import CreateItem, DeleteItem, UpdateItem
from example_service.application.queries.items import GetItem, ListItems
from example_service.container import build_mediator
from example_service.domain.item import Item, ItemIsDoneError, ItemNotFoundError, ItemStatus
from platform_common.context import RequestContext
from platform_common.errors import PermissionDeniedError, UnauthenticatedError, ValidationError
from platform_common.mediator import Mediator
from tests.fakes import FakeUnitOfWork, FakeUserDirectory

ALICE = uuid4()
BOB = uuid4()


def ctx(user: UUID | None, role: str = "user") -> RequestContext:
    return RequestContext("t", actor_user_id=user, actor_role=role if user else None)


@pytest.fixture
def store() -> dict[UUID, Item]:
    return {}


@pytest.fixture
def mediator(store: dict[UUID, Item]) -> Mediator:
    return build_mediator(lambda: FakeUnitOfWork(store), FakeUserDirectory({ALICE: "Alice"}))


async def test_create_and_get_with_owner_name(mediator: Mediator) -> None:
    created = await mediator.send(CreateItem(ctx(ALICE), "  Buy milk ", "2l"))
    assert created.title == "Buy milk" and created.status is ItemStatus.OPEN
    got = await mediator.send(GetItem(ctx(ALICE), created.id))
    assert got.owner_name == "Alice"


async def test_requires_auth_and_ownership(mediator: Mediator) -> None:
    with pytest.raises(UnauthenticatedError):
        await mediator.send(CreateItem(ctx(None), "x"))
    item = await mediator.send(CreateItem(ctx(ALICE), "x"))
    with pytest.raises(PermissionDeniedError):
        await mediator.send(GetItem(ctx(BOB), item.id))
    # админ может всё
    await mediator.send(GetItem(ctx(BOB, "admin"), item.id))


async def test_validation(mediator: Mediator) -> None:
    with pytest.raises(ValidationError) as exc_info:
        await mediator.send(CreateItem(ctx(ALICE), "   "))
    assert exc_info.value.details[0].field == "title"


async def test_status_transition_rules(mediator: Mediator) -> None:
    item = await mediator.send(CreateItem(ctx(ALICE), "task"))
    done = await mediator.send(UpdateItem(ctx(ALICE), item.id, status=ItemStatus.DONE))
    assert done.status is ItemStatus.DONE
    with pytest.raises(ItemIsDoneError):
        await mediator.send(UpdateItem(ctx(ALICE), item.id, title="new"))
    with pytest.raises(ItemIsDoneError):
        await mediator.send(UpdateItem(ctx(ALICE), item.id, status=ItemStatus.OPEN))


async def test_list_pagination_and_visibility(mediator: Mediator) -> None:
    for i in range(3):
        await mediator.send(CreateItem(ctx(ALICE), f"a{i}"))
    await mediator.send(CreateItem(ctx(BOB), "b"))

    first = await mediator.send(ListItems(ctx(ALICE), limit=2))
    assert len(first.items) == 2 and first.next_cursor
    second = await mediator.send(ListItems(ctx(ALICE), limit=2, cursor=first.next_cursor))
    assert len(second.items) == 1 and second.next_cursor == ""

    everything = await mediator.send(ListItems(ctx(BOB, "admin"), limit=10))
    assert len(everything.items) == 4


async def test_delete(mediator: Mediator) -> None:
    item = await mediator.send(CreateItem(ctx(ALICE), "x"))
    with pytest.raises(PermissionDeniedError):
        await mediator.send(DeleteItem(ctx(BOB), item.id))
    await mediator.send(DeleteItem(ctx(ALICE), item.id))
    with pytest.raises(ItemNotFoundError):
        await mediator.send(GetItem(ctx(ALICE), item.id))

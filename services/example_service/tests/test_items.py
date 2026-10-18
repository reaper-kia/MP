from uuid import UUID, uuid4

import pytest

from example_service.applications.commands.create_item import CreateItemCommand
from example_service.applications.commands.delete_item import DeleteItemCommand
from example_service.applications.commands.update_item import UpdateItemCommand
from example_service.applications.context import RequestContext
from example_service.applications.exceptions import (
    ItemNotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)
from example_service.applications.mediator import Mediator
from example_service.applications.queries.get_item import GetItemQuery
from example_service.applications.queries.list_items import ListItemsQuery
from example_service.dependencies import build_mediator
from example_service.domain.entities import Item
from example_service.domain.exceptions import InvalidItemTitleError, ItemAlreadyDoneError
from tests.fakes import FakeUnitOfWork, FakeUserDirectory

ALICE = uuid4()
BOB = uuid4()


def ctx(user: UUID | None, role: str = "user") -> RequestContext:
    return RequestContext("t", actor_user_id=user, actor_role=role if user else None)


@pytest.fixture
def mediator() -> Mediator:
    store: dict[UUID, Item] = {}
    return build_mediator(lambda: FakeUnitOfWork(store), FakeUserDirectory({ALICE: "Alice"}))


async def test_create_and_get_with_owner_name(mediator: Mediator) -> None:
    created = await mediator.send(CreateItemCommand(ctx(ALICE), "  Buy milk ", "2l"))
    assert created.title == "Buy milk" and created.status == "open"
    got = await mediator.send(GetItemQuery(ctx(ALICE), created.id))
    assert got.owner_name == "Alice"


async def test_auth_and_ownership(mediator: Mediator) -> None:
    with pytest.raises(UnauthenticatedError):
        await mediator.send(CreateItemCommand(ctx(None), "x"))
    item = await mediator.send(CreateItemCommand(ctx(ALICE), "x"))
    with pytest.raises(PermissionDeniedError):
        await mediator.send(GetItemQuery(ctx(BOB), item.id))
    await mediator.send(GetItemQuery(ctx(BOB, "admin"), item.id))  # админу можно


async def test_title_validation(mediator: Mediator) -> None:
    with pytest.raises(InvalidItemTitleError):
        await mediator.send(CreateItemCommand(ctx(ALICE), "   "))


async def test_done_item_is_frozen(mediator: Mediator) -> None:
    item = await mediator.send(CreateItemCommand(ctx(ALICE), "task"))
    done = await mediator.send(UpdateItemCommand(ctx(ALICE), item.id, status="done"))
    assert done.status == "done"
    with pytest.raises(ItemAlreadyDoneError):
        await mediator.send(UpdateItemCommand(ctx(ALICE), item.id, title="new"))
    with pytest.raises(ItemAlreadyDoneError):
        await mediator.send(UpdateItemCommand(ctx(ALICE), item.id, status="open"))


async def test_list_pagination_and_visibility(mediator: Mediator) -> None:
    for i in range(3):
        await mediator.send(CreateItemCommand(ctx(ALICE), f"a{i}"))
    await mediator.send(CreateItemCommand(ctx(BOB), "b"))

    first = await mediator.send(ListItemsQuery(ctx(ALICE), limit=2))
    assert len(first.items) == 2 and first.has_more
    second = await mediator.send(ListItemsQuery(ctx(ALICE), limit=2, offset=2))
    assert len(second.items) == 1 and not second.has_more
    assert len((await mediator.send(ListItemsQuery(ctx(BOB, "admin"), limit=10))).items) == 4


async def test_delete(mediator: Mediator) -> None:
    item = await mediator.send(CreateItemCommand(ctx(ALICE), "x"))
    with pytest.raises(PermissionDeniedError):
        await mediator.send(DeleteItemCommand(ctx(BOB), item.id))
    await mediator.send(DeleteItemCommand(ctx(ALICE), item.id))
    with pytest.raises(ItemNotFoundError):
        await mediator.send(GetItemQuery(ctx(ALICE), item.id))

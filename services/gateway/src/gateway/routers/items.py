"""Образец роутера: HTTP DTO → proto → gRPC → proto → HTTP DTO. Логики нет."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from contracts.common.v1 import common_pb2
from contracts.example.v1 import example_pb2 as pb
from gateway.dependencies import AuthCtx, Clients
from gateway.schemas.common import ERRORS, Page
from gateway.schemas.items import STATUS_TO_PB, ItemCreateIn, ItemOut, ItemStatus, ItemUpdateIn

router = APIRouter(prefix="/api/v1/items", tags=["items"], responses=ERRORS)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreateIn, ctx: AuthCtx, clients: Clients, request: Request
) -> ItemOut:
    resp = await clients.example.CreateItem(
        pb.CreateItemRequest(context=ctx, title=body.title, description=body.description)
    )
    item = ItemOut.from_pb(resp.item)
    # realtime: все вкладки владельца получат событие по WebSocket
    await request.app.state.ws.send_to_user(
        item.owner_id, "item.created", item.model_dump(mode="json")
    )
    return item


@router.get("")
async def list_items(
    ctx: AuthCtx,
    clients: Clients,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str = "",
    item_status: Annotated[ItemStatus | None, Query(alias="status")] = None,
) -> Page[ItemOut]:
    resp = await clients.example.ListItems(
        pb.ListItemsRequest(
            context=ctx,
            page=common_pb2.PageRequest(limit=limit, cursor=cursor),
            status=STATUS_TO_PB[item_status] if item_status else pb.ITEM_STATUS_UNSPECIFIED,
        )
    )
    return Page[ItemOut](
        items=[ItemOut.from_pb(i) for i in resp.items], next_cursor=resp.page.next_cursor or None
    )


@router.get("/{item_id}")
async def get_item(item_id: UUID, ctx: AuthCtx, clients: Clients) -> ItemOut:
    resp = await clients.example.GetItem(pb.GetItemRequest(context=ctx, item_id=str(item_id)))
    return ItemOut.from_pb(resp.item)


@router.patch("/{item_id}")
async def update_item(item_id: UUID, body: ItemUpdateIn, ctx: AuthCtx, clients: Clients) -> ItemOut:
    req = pb.UpdateItemRequest(context=ctx, item_id=str(item_id))
    if body.title is not None:
        req.title = body.title
    if body.description is not None:
        req.description = body.description
    if body.status is not None:
        req.status = STATUS_TO_PB[body.status]
    resp = await clients.example.UpdateItem(req)
    return ItemOut.from_pb(resp.item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, ctx: AuthCtx, clients: Clients) -> None:
    await clients.example.DeleteItem(pb.DeleteItemRequest(context=ctx, item_id=str(item_id)))

"""Образец роутера: HTTP-схема → proto-запрос → gRPC → proto-ответ → HTTP-схема. Логики нет."""

from typing import Annotated
from uuid import UUID

from example.v1 import example_service_pb2 as pb
from fastapi import APIRouter, Query, Request, status

from gateway.dependencies import AuthCtx, Clients
from gateway.schemas.common import ERRORS
from gateway.schemas.items import STATUS_TO_PROTO, ItemCreateIn, ItemOut, ItemPageOut, ItemUpdateIn

router = APIRouter(prefix="/api/v1/items", tags=["items"], responses=ERRORS)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreateIn, ctx: AuthCtx, clients: Clients, request: Request
) -> ItemOut:
    result = await clients.example.CreateItem(
        pb.CreateItemRequest(context=ctx, title=body.title, description=body.description)
    )
    item = ItemOut.from_proto(result.item)
    # realtime: все открытые вкладки владельца получат событие по WebSocket
    await request.app.state.ws.send_to_user(
        item.owner_id, "item.created", item.model_dump(mode="json")
    )
    return item


@router.get("")
async def list_items(
    ctx: AuthCtx,
    clients: Clients,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPageOut:
    result = await clients.example.ListItems(
        pb.ListItemsRequest(context=ctx, limit=limit, offset=offset)
    )
    return ItemPageOut(
        items=[ItemOut.from_proto(i) for i in result.items], has_more=result.has_more
    )


@router.get("/{item_id}")
async def get_item(item_id: UUID, ctx: AuthCtx, clients: Clients) -> ItemOut:
    result = await clients.example.GetItem(pb.GetItemRequest(context=ctx, item_id=str(item_id)))
    return ItemOut.from_proto(result.item)


@router.patch("/{item_id}")
async def update_item(item_id: UUID, body: ItemUpdateIn, ctx: AuthCtx, clients: Clients) -> ItemOut:
    req = pb.UpdateItemRequest(context=ctx, item_id=str(item_id))
    if body.title is not None:
        req.title = body.title
    if body.description is not None:
        req.description = body.description
    if body.status is not None:
        req.status = STATUS_TO_PROTO[body.status]
    result = await clients.example.UpdateItem(req)
    return ItemOut.from_proto(result.item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, ctx: AuthCtx, clients: Clients) -> None:
    await clients.example.DeleteItem(pb.DeleteItemRequest(context=ctx, item_id=str(item_id)))

"""Обработчики команд клиента по WebSocket.

Клиент шлёт:   {"type": "group.join", "request_id": "uuid", "payload": {...}}
Сервер отвечает: {"type": "<type>.ok", "request_id": "uuid", "payload": {...}}
или ошибкой:   {"type": "error", "request_id": "uuid", "payload": {"code", "message", "details"}}

Новый обработчик:

    @ws_handler("room.bet")
    async def place_bet(conn, payload, app) -> dict:
        resp = await app.state.clients.casino.PlaceBet(...)   # ошибки gRPC → "error"
        return {...}
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

from contracts.example.v1 import example_pb2
from gateway.errors import ApiError
from gateway.schemas.items import ItemOut
from gateway.ws.manager import Connection

type WsHandler = Callable[[Connection, dict[str, Any], FastAPI, str], Awaitable[Any]]

HANDLERS: dict[str, WsHandler] = {}


def ws_handler(type_: str) -> Callable[[WsHandler], WsHandler]:
    def decorator(fn: WsHandler) -> WsHandler:
        HANDLERS[type_] = fn
        return fn

    return decorator


def _group(payload: dict[str, Any]) -> str:
    group = payload.get("group")
    if not isinstance(group, str) or not 0 < len(group) <= 128:
        raise ApiError(422, "VALIDATION_ERROR", "payload.group must be a non-empty string")
    return group


@ws_handler("ping")
async def ping(conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str) -> Any:
    return {"pong": True}


@ws_handler("group.join")
async def join(conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str) -> Any:
    group = _group(payload)
    app.state.ws.join(conn, group)
    return {"group": group}


@ws_handler("group.leave")
async def leave(conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str) -> Any:
    group = _group(payload)
    app.state.ws.leave(conn, group)
    return {"group": group}


@ws_handler("group.say")
async def say(conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str) -> Any:
    """Пример broadcast: сообщение всем в группе."""
    group = _group(payload)
    if group not in conn.groups:
        raise ApiError(409, "NOT_IN_GROUP", "Join the group first")
    await app.state.ws.broadcast(
        group,
        "group.message",
        {"group": group, "from": str(conn.user_id), "text": payload.get("text", "")},
    )
    return None


@ws_handler("item.get")
async def get_item(conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str) -> Any:
    """Пример gRPC-вызова из WebSocket."""
    resp = await app.state.clients.example.GetItem(
        example_pb2.GetItemRequest(
            context=conn_context(conn, request_id), item_id=str(payload.get("item_id", ""))
        )
    )
    return ItemOut.from_pb(resp.item).model_dump(mode="json")


def conn_context(conn: Connection, request_id: str) -> Any:
    from gateway.dependencies import Actor, build_context

    return build_context(request_id, Actor(conn.user_id, conn.role))

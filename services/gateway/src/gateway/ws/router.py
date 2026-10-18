import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from grpc import aio

from gateway.errors import ApiError, app_error_to_api, rpc_error_to_api
from gateway.ws.handlers import HANDLERS
from gateway.ws.manager import Connection
from platform_common.context import request_id_var
from platform_common.errors import AppError
from platform_common.security.jwt import JwtCodec

logger = logging.getLogger(__name__)
router = APIRouter()

WS_UNAUTHORIZED = 4401


@router.websocket("/ws/v1")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    """Подключение: ws://host/ws/v1?token=<access_token>"""
    jwt: JwtCodec = websocket.app.state.jwt
    try:
        claims = jwt.decode(token)
    except AppError:
        # accept + close, чтобы браузер увидел код 4401, а не безликий 403
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="invalid token")
        return

    await websocket.accept()
    manager = websocket.app.state.ws
    conn = Connection(websocket=websocket, user_id=claims.user_id, role=claims.role)
    manager.connect(conn)
    await conn.send("session.ready", {"user_id": str(conn.user_id)})
    try:
        while True:
            message = await websocket.receive_json()
            await _dispatch(conn, message, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(conn)


async def _dispatch(conn: Connection, message: Any, websocket: WebSocket) -> None:
    if not isinstance(message, dict):
        await conn.send("error", _err(ApiError(400, "BAD_REQUEST", "Message must be an object")))
        return
    request_id = str(message.get("request_id") or uuid4())
    request_id_var.set(request_id)
    type_ = str(message.get("type", ""))
    handler = HANDLERS.get(type_)
    if handler is None:
        await conn.send(
            "error", _err(ApiError(400, "UNKNOWN_TYPE", f"Unknown type {type_!r}")), request_id
        )
        return
    payload = message.get("payload") or {}
    try:
        result = await handler(
            conn, payload if isinstance(payload, dict) else {}, websocket.app, request_id
        )
    except ApiError as exc:
        await conn.send("error", _err(exc), request_id)
    except aio.AioRpcError as exc:
        await conn.send("error", _err(rpc_error_to_api(exc)), request_id)
    except AppError as exc:
        await conn.send("error", _err(app_error_to_api(exc)), request_id)
    except Exception:
        logger.exception("WebSocket handler %s failed", type_)
        await conn.send("error", _err(ApiError(500, "INTERNAL", "Internal error")), request_id)
    else:
        await conn.send(f"{type_}.ok", result, request_id)


def _err(exc: ApiError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "details": [{"field": d.field, "reason": d.reason} for d in exc.details],
    }

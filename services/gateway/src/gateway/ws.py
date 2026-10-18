"""WebSocket: ws://host/ws/v1?token=<access_token>

Сервер шлёт события {"type": "...", "payload": {...}}. Клиент может прислать {"type": "ping"}.
Отправить событие из любого роутера: await request.app.state.ws.send_to_user(user_id, type, payload)
Ограничение: одна реплика gateway (подключения хранятся в памяти процесса).
"""

import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from gateway.config import get_settings
from gateway.errors import ApiError
from gateway.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._by_user: dict[UUID, set[WebSocket]] = defaultdict(set)

    def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        self._by_user[user_id].add(websocket)

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        self._by_user[user_id].discard(websocket)
        if not self._by_user[user_id]:
            del self._by_user[user_id]

    async def send_to_user(self, user_id: UUID, type_: str, payload: Any) -> None:
        for websocket in list(self._by_user.get(user_id, ())):
            try:
                await websocket.send_json({"type": type_, "payload": payload})
            except Exception:
                self.disconnect(user_id, websocket)

    async def broadcast(self, type_: str, payload: Any) -> None:
        for user_id in list(self._by_user):
            await self.send_to_user(user_id, type_, payload)


@router.websocket("/ws/v1")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    await websocket.accept()
    try:
        actor = decode_access_token(token, get_settings())
    except ApiError:
        await websocket.close(code=4401, reason="invalid token")
        return

    manager: ConnectionManager = websocket.app.state.ws
    manager.connect(actor.user_id, websocket)
    await websocket.send_json({"type": "ready", "payload": {"user_id": str(actor.user_id)}})
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(actor.user_id, websocket)

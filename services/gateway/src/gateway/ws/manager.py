"""Реестр WebSocket-подключений этого процесса.

Ограничение: одна реплика Gateway. Для нескольких — публикуй события в Redis pub/sub
и раздавай локальным подключениям (интерфейс send_to_user/broadcast не поменяется).
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    user_id: UUID
    role: str
    id: UUID = field(default_factory=uuid4)
    groups: set[str] = field(default_factory=set)

    async def send(self, type_: str, payload: Any, request_id: str | None = None) -> None:
        await self.websocket.send_json(
            {"type": type_, "request_id": request_id, "payload": payload}
        )


class ConnectionManager:
    def __init__(self) -> None:
        self._by_user: dict[UUID, set[Connection]] = defaultdict(set)
        self._groups: dict[str, set[Connection]] = defaultdict(set)

    def connect(self, conn: Connection) -> None:
        self._by_user[conn.user_id].add(conn)

    def disconnect(self, conn: Connection) -> None:
        self._by_user[conn.user_id].discard(conn)
        if not self._by_user[conn.user_id]:
            del self._by_user[conn.user_id]
        for group in list(conn.groups):
            self.leave(conn, group)

    def join(self, conn: Connection, group: str) -> None:
        conn.groups.add(group)
        self._groups[group].add(conn)

    def leave(self, conn: Connection, group: str) -> None:
        conn.groups.discard(group)
        members = self._groups.get(group)
        if members is not None:
            members.discard(conn)
            if not members:
                del self._groups[group]

    async def send_to_user(self, user_id: UUID, type_: str, payload: Any) -> None:
        await self._fanout(list(self._by_user.get(user_id, ())), type_, payload)

    async def broadcast(self, group: str, type_: str, payload: Any) -> None:
        await self._fanout(list(self._groups.get(group, ())), type_, payload)

    @property
    def online_users(self) -> int:
        return len(self._by_user)

    async def _fanout(self, conns: list[Connection], type_: str, payload: Any) -> None:
        results = await asyncio.gather(
            *(c.send(type_, payload) for c in conns), return_exceptions=True
        )
        for conn, result in zip(conns, results, strict=True):
            if isinstance(result, Exception):
                logger.info("Drop dead websocket %s: %s", conn.id, result)
                self.disconnect(conn)

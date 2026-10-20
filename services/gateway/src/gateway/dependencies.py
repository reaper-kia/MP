"""Зависимости для роутеров. Используются как типы аргументов:

async def handler(ctx: Ctx, clients: Clients, settings: AppSettings): ...

Авторизации в продукте нет (по ТЗ). RequestContext несёт request_id — для логов сервисов — и
анонимный id браузера (заголовок X-Client-Id → actor_user_id): по нему история поисков у каждого
своя. Это не вход и не защита: id выдаёт сам фронт, случайный, хранится в браузере.
"""

import re
from typing import Annotated

from common.v1 import common_pb2
from fastapi import Depends, Request

from gateway.config import Settings, get_settings
from gateway.grpc_clients import GrpcClients


def get_clients(request: Request) -> GrpcClients:
    clients: GrpcClients = request.app.state.clients
    return clients


CLIENT_ID_HEADER = "X-Client-Id"
_CLIENT_ID = re.compile(r"[A-Za-z0-9-]{8,64}")


def client_id(request: Request) -> str:
    """X-Client-Id от фронта; пусто или мусор — пустая строка (история будет пустой)."""
    value = request.headers.get(CLIENT_ID_HEADER, "").strip()
    return value if _CLIENT_ID.fullmatch(value) else ""


def request_context(request: Request) -> common_pb2.RequestContext:
    return common_pb2.RequestContext(
        request_id=request.state.request_id, actor_user_id=client_id(request)
    )


Clients = Annotated[GrpcClients, Depends(get_clients)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Ctx = Annotated[common_pb2.RequestContext, Depends(request_context)]

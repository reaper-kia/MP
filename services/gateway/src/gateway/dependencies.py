"""Зависимости для роутеров. Используются как типы аргументов:

async def handler(ctx: Ctx, clients: Clients, settings: AppSettings): ...

Авторизации в продукте нет (по ТЗ). RequestContext несёт только request_id — для логов сервисов.
"""

from typing import Annotated

from common.v1 import common_pb2
from fastapi import Depends, Request

from gateway.config import Settings, get_settings
from gateway.grpc_clients import GrpcClients


def get_clients(request: Request) -> GrpcClients:
    clients: GrpcClients = request.app.state.clients
    return clients


def request_context(request: Request) -> common_pb2.RequestContext:
    return common_pb2.RequestContext(request_id=request.state.request_id)


Clients = Annotated[GrpcClients, Depends(get_clients)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Ctx = Annotated[common_pb2.RequestContext, Depends(request_context)]

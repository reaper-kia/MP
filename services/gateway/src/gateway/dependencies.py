"""Зависимости для роутеров. Используются как типы аргументов:

async def handler(ctx: AuthCtx, clients: Clients): ...   # нужен логин
async def handler(ctx: AnonCtx, clients: Clients): ...   # можно без логина
"""

from typing import Annotated

from common.v1 import common_pb2
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway.config import Settings, get_settings
from gateway.errors import ApiError
from gateway.grpc_clients import GrpcClients
from gateway.security import Actor, decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_clients(request: Request) -> GrpcClients:
    clients: GrpcClients = request.app.state.clients
    return clients


def optional_actor(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Actor | None:
    if credentials is None:
        return None
    return decode_access_token(credentials.credentials, settings)


def current_actor(actor: Annotated[Actor | None, Depends(optional_actor)]) -> Actor:
    if actor is None:
        raise ApiError(401, "UNAUTHENTICATED", "Bearer access token is required")
    return actor


def build_context(request_id: str, actor: Actor | None) -> common_pb2.RequestContext:
    """RequestContext для сервисов. Actor берём только из проверенного токена."""
    return common_pb2.RequestContext(
        request_id=request_id,
        actor_user_id=str(actor.user_id) if actor else "",
        actor_role=actor.role if actor else "",
    )


def anon_context(
    request: Request, actor: Annotated[Actor | None, Depends(optional_actor)]
) -> common_pb2.RequestContext:
    return build_context(request.state.request_id, actor)


def auth_context(
    request: Request, actor: Annotated[Actor, Depends(current_actor)]
) -> common_pb2.RequestContext:
    return build_context(request.state.request_id, actor)


Clients = Annotated[GrpcClients, Depends(get_clients)]
AppSettings = Annotated[Settings, Depends(get_settings)]
CurrentActor = Annotated[Actor, Depends(current_actor)]
AuthCtx = Annotated[common_pb2.RequestContext, Depends(auth_context)]
AnonCtx = Annotated[common_pb2.RequestContext, Depends(anon_context)]

"""FastAPI-зависимости. В роутерах используются как типы:

async def handler(ctx: AuthCtx, clients: Clients): ...      # нужен логин
async def handler(ctx: AnonCtx, clients: Clients): ...      # можно без логина
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from contracts.common.v1 import common_pb2
from gateway.clients import GrpcClients
from gateway.config import Settings
from gateway.errors import ApiError
from platform_common.security.jwt import JwtCodec

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: UUID
    role: str


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clients(request: Request) -> GrpcClients:
    clients: GrpcClients = request.app.state.clients
    return clients


def get_jwt(request: Request) -> JwtCodec:
    codec: JwtCodec = request.app.state.jwt
    return codec


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def optional_actor(
    jwt: Annotated[JwtCodec, Depends(get_jwt)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Actor | None:
    if credentials is None:
        return None
    claims = jwt.decode(credentials.credentials)  # InvalidTokenError → 401 (errors.py)
    return Actor(user_id=claims.user_id, role=claims.role)


def current_actor(actor: Annotated[Actor | None, Depends(optional_actor)]) -> Actor:
    if actor is None:
        raise ApiError(401, "UNAUTHENTICATED", "Bearer access token is required")
    return actor


def build_context(request_id: str, actor: Actor | None) -> common_pb2.RequestContext:
    return common_pb2.RequestContext(
        request_id=request_id,
        actor_user_id=str(actor.user_id) if actor else "",
        actor_role=actor.role if actor else "",
    )


def anon_context(
    request: Request, actor: Annotated[Actor | None, Depends(optional_actor)]
) -> common_pb2.RequestContext:
    return build_context(_request_id(request), actor)


def auth_context(
    request: Request, actor: Annotated[Actor, Depends(current_actor)]
) -> common_pb2.RequestContext:
    return build_context(_request_id(request), actor)


Clients = Annotated[GrpcClients, Depends(get_clients)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
CurrentActor = Annotated[Actor, Depends(current_actor)]
AuthCtx = Annotated[common_pb2.RequestContext, Depends(auth_context)]
AnonCtx = Annotated[common_pb2.RequestContext, Depends(anon_context)]

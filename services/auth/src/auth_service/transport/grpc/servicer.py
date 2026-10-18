"""Тонкий транспортный слой: proto → команда → mediator → proto. Без логики."""

from uuid import UUID

from auth_service.application.commands.login_user import LoginUser
from auth_service.application.commands.logout_user import LogoutUser
from auth_service.application.commands.refresh_tokens import RefreshTokens
from auth_service.application.commands.register_user import RegisterUser
from auth_service.application.queries.get_user import GetUser
from auth_service.transport.grpc.mappers import tokens_to_pb, user_to_pb
from contracts.auth.v1 import auth_pb2 as pb
from contracts.auth.v1 import auth_pb2_grpc as pb_grpc
from platform_common.context import RequestContext
from platform_common.errors import ValidationError
from platform_common.grpc.errors import ServicerContext, rpc
from platform_common.mediator import Mediator


def _uuid_or_none(value: str, field: str) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValidationError.field(field, "invalid_uuid") from exc


class AuthServicer(pb_grpc.AuthServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._m = mediator

    @rpc
    async def Register(
        self, request: pb.RegisterRequest, context: ServicerContext
    ) -> pb.RegisterResponse:
        result = await self._m.send(
            RegisterUser(
                ctx=RequestContext.from_proto(request.context),
                email=request.email,
                name=request.name,
                password=request.password,
            )
        )
        return pb.RegisterResponse(user=user_to_pb(result.user), tokens=tokens_to_pb(result.tokens))

    @rpc
    async def Login(self, request: pb.LoginRequest, context: ServicerContext) -> pb.LoginResponse:
        result = await self._m.send(
            LoginUser(
                ctx=RequestContext.from_proto(request.context),
                email=request.email,
                password=request.password,
            )
        )
        return pb.LoginResponse(user=user_to_pb(result.user), tokens=tokens_to_pb(result.tokens))

    @rpc
    async def Refresh(
        self, request: pb.RefreshRequest, context: ServicerContext
    ) -> pb.RefreshResponse:
        tokens = await self._m.send(
            RefreshTokens(RequestContext.from_proto(request.context), request.refresh_token)
        )
        return pb.RefreshResponse(tokens=tokens_to_pb(tokens))

    @rpc
    async def Logout(
        self, request: pb.LogoutRequest, context: ServicerContext
    ) -> pb.LogoutResponse:
        await self._m.send(
            LogoutUser(RequestContext.from_proto(request.context), request.refresh_token)
        )
        return pb.LogoutResponse()

    @rpc
    async def GetUser(
        self, request: pb.GetUserRequest, context: ServicerContext
    ) -> pb.GetUserResponse:
        user = await self._m.send(
            GetUser(
                RequestContext.from_proto(request.context),
                _uuid_or_none(request.user_id, "user_id"),
            )
        )
        return pb.GetUserResponse(user=user_to_pb(user))

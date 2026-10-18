import logging
from uuid import UUID

from auth.v1 import auth_service_pb2 as pb
from auth.v1 import auth_service_pb2_grpc as pb_grpc

from auth_service.applications.commands.login_user import LoginUserCommand
from auth_service.applications.commands.logout_user import LogoutUserCommand
from auth_service.applications.commands.refresh_token import RefreshTokenCommand
from auth_service.applications.commands.register_user import RegisterUserCommand
from auth_service.applications.exceptions import UserNotFoundError
from auth_service.applications.mediator import Mediator
from auth_service.applications.queries.get_user import GetUserQuery
from auth_service.transport.grpc.errors import Context, grpc_errors
from auth_service.transport.grpc.mappers import context_from_proto, tokens_to_proto, user_to_proto

logger = logging.getLogger(__name__)


class AuthServicer(pb_grpc.AuthServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    @grpc_errors
    async def Register(self, request: pb.RegisterRequest, context: Context) -> pb.RegisterResponse:
        logger.info("Register request_id=%s", request.context.request_id)
        result = await self._mediator.send(
            RegisterUserCommand(
                ctx=context_from_proto(request.context),
                email=request.email,
                name=request.name,
                password=request.password,
            )
        )
        return pb.RegisterResponse(
            user=user_to_proto(result.user), tokens=tokens_to_proto(result.tokens)
        )

    @grpc_errors
    async def Login(self, request: pb.LoginRequest, context: Context) -> pb.LoginResponse:
        logger.info("Login request_id=%s", request.context.request_id)
        result = await self._mediator.send(
            LoginUserCommand(
                ctx=context_from_proto(request.context),
                email=request.email,
                password=request.password,
            )
        )
        return pb.LoginResponse(
            user=user_to_proto(result.user), tokens=tokens_to_proto(result.tokens)
        )

    @grpc_errors
    async def Refresh(self, request: pb.RefreshRequest, context: Context) -> pb.RefreshResponse:
        tokens = await self._mediator.send(
            RefreshTokenCommand(
                ctx=context_from_proto(request.context), refresh_token=request.refresh_token
            )
        )
        return pb.RefreshResponse(tokens=tokens_to_proto(tokens))

    @grpc_errors
    async def Logout(self, request: pb.LogoutRequest, context: Context) -> pb.LogoutResponse:
        await self._mediator.send(
            LogoutUserCommand(
                ctx=context_from_proto(request.context), refresh_token=request.refresh_token
            )
        )
        return pb.LogoutResponse()

    @grpc_errors
    async def GetUser(self, request: pb.GetUserRequest, context: Context) -> pb.GetUserResponse:
        try:
            user_id = UUID(request.user_id) if request.user_id else None
        except ValueError as exc:
            raise UserNotFoundError("User not found") from exc
        user = await self._mediator.send(
            GetUserQuery(ctx=context_from_proto(request.context), user_id=user_id)
        )
        return pb.GetUserResponse(user=user_to_proto(user))

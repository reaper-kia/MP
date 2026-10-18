"""gRPC-клиент к auth_service — образец вызова одного сервиса из другого.

Передаём тот же RequestContext (кто делает запрос), таймаут — на каждый вызов.
Если auth недоступен, не падаем: имя владельца не критично (деградация).
"""

import logging
from uuid import UUID

import grpc
from auth.v1 import auth_service_pb2 as auth_pb
from auth.v1 import auth_service_pb2_grpc as auth_grpc
from common.v1 import common_pb2

from example_service.applications.context import RequestContext
from example_service.applications.ports.user_directory import UserDirectory

logger = logging.getLogger(__name__)


class GrpcUserDirectory(UserDirectory):
    def __init__(self, channel: grpc.aio.Channel, timeout: float) -> None:
        self._stub = auth_grpc.AuthServiceStub(channel)
        self._timeout = timeout

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None:
        request = auth_pb.GetUserRequest(
            context=common_pb2.RequestContext(
                request_id=ctx.request_id,
                actor_user_id=str(ctx.actor_user_id) if ctx.actor_user_id else "",
                actor_role=ctx.actor_role or "",
            ),
            user_id=str(user_id),
        )
        try:
            response: auth_pb.GetUserResponse = await self._stub.GetUser(
                request, timeout=self._timeout
            )
        except grpc.aio.AioRpcError as e:
            logger.warning("auth.GetUser failed: %s %s", e.code().name, e.details())
            return None
        return response.user.name

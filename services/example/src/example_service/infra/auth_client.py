"""Адаптер порта UserDirectory поверх gRPC-клиента Auth.

Шаблон межсервисного вызова: прокидываем RequestContext, таймаут задаёт канал,
ошибку соседа либо пробрасываем (app_error_from_rpc), либо деградируем — как здесь.
"""

import logging
from uuid import UUID

from grpc import aio

from contracts.auth.v1 import auth_pb2, auth_pb2_grpc
from platform_common.context import RequestContext
from platform_common.grpc.errors import parse_rpc_error

logger = logging.getLogger(__name__)


class GrpcUserDirectory:
    def __init__(self, channel: aio.Channel) -> None:
        self._stub = auth_pb2_grpc.AuthServiceStub(channel)

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None:
        try:
            resp: auth_pb2.GetUserResponse = await self._stub.GetUser(
                auth_pb2.GetUserRequest(context=ctx.to_proto(), user_id=str(user_id))
            )
        except aio.AioRpcError as exc:
            info = parse_rpc_error(exc)
            logger.warning("Auth.GetUser failed: %s %s", info.status.name, info.code)
            return None  # имя владельца — не критично, отдаём item без него
        return resp.user.name

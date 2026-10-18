"""gRPC-клиенты ко всем сервисам. Один канал на сервис, создаются при старте gateway.

Новый сервис: добавь адрес в config.py и строку self.<name> = ... ниже.
"""

from collections.abc import Callable
from typing import Any

import grpc
from auth.v1 import auth_service_pb2_grpc
from example.v1 import example_service_pb2_grpc

from gateway.config import Settings


class DefaultTimeoutInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Каждому вызову ставит таймаут, если его не передали явно."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    async def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, Any], Any],
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout or self._timeout,
            metadata=client_call_details.metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )
        return await continuation(details, request)


class GrpcClients:
    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.grpc_timeout_seconds
        self.channels: dict[str, grpc.aio.Channel] = {}

        self.auth: Any = auth_service_pb2_grpc.AuthServiceStub(
            self._channel("auth", settings.auth_grpc_target)
        )
        self.example: Any = example_service_pb2_grpc.ExampleServiceStub(
            self._channel("example", settings.example_grpc_target)
        )

    def _channel(self, name: str, target: str) -> grpc.aio.Channel:
        channel = grpc.aio.insecure_channel(
            target, interceptors=[DefaultTimeoutInterceptor(self._timeout)]
        )
        self.channels[name] = channel
        return channel

    async def close(self) -> None:
        for channel in self.channels.values():
            await channel.close()

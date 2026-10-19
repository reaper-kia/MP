from collections.abc import Callable
from typing import Any

import grpc
from collector.v1 import collector_service_pb2_grpc
from ml.v1 import ml_service_pb2_grpc
from search.v1 import search_service_pb2_grpc

from gateway.config import Settings

# экспорт XLSX/DOCX может быть больше дефолтных 4 МБ
MAX_MESSAGE_BYTES = 32 * 1024 * 1024


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

        self.search: Any = search_service_pb2_grpc.SearchServiceStub(
            self._channel("search", settings.search_grpc_target)
        )
        self.collector: Any = collector_service_pb2_grpc.CollectorServiceStub(
            self._channel("collector", settings.collector_grpc_target)
        )
        self.ml: Any = ml_service_pb2_grpc.MlServiceStub(
            self._channel("ml", settings.ml_grpc_target)
        )

    def _channel(self, name: str, target: str) -> grpc.aio.Channel:
        channel = grpc.aio.insecure_channel(
            target,
            interceptors=[DefaultTimeoutInterceptor(self._timeout)],
            options=[("grpc.max_receive_message_length", MAX_MESSAGE_BYTES)],
        )
        self.channels[name] = channel
        return channel

    async def close(self) -> None:
        for channel in self.channels.values():
            await channel.close()

"""Исходящие gRPC-каналы: дефолтный таймаут + x-request-id в metadata."""

from collections.abc import Callable
from typing import Any

from grpc import aio

from platform_common.context import request_id_var


class _DefaultsInterceptor(aio.UnaryUnaryClientInterceptor):  # type: ignore[misc]
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    async def intercept_unary_unary(
        self,
        continuation: Callable[[aio.ClientCallDetails, Any], Any],
        client_call_details: aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        metadata = aio.Metadata(*(client_call_details.metadata or ()))
        request_id = request_id_var.get()
        if request_id != "-" and not metadata.get_all("x-request-id"):
            metadata.add("x-request-id", request_id)
        details = aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout or self._timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )
        return await continuation(details, request)


def create_channel(target: str, *, timeout: float = 5.0) -> aio.Channel:
    """Канал создаётся лениво: соединение установится при первом вызове,
    поэтому порядок старта сервисов не важен."""
    return aio.insecure_channel(
        target,
        options=[
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.enable_retries", 1),
            ("grpc.lb_policy_name", "round_robin"),
        ],
        interceptors=[_DefaultsInterceptor(timeout)],
    )

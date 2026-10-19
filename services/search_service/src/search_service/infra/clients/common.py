"""Общее для gRPC-клиентов: контекст, Timestamp, ошибки соседей → UpstreamError."""

from datetime import UTC, datetime

import grpc
from common.v1 import common_pb2, platform_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from search_service.applications.exceptions import UpstreamError
from search_service.applications.request_context import current_request_id
from search_service.domain.enums import Platform
from search_service.domain.value_objects import UtcPeriod

PLATFORM_TO_PROTO: dict[Platform, platform_pb2.Platform] = {
    Platform.VK: platform_pb2.PLATFORM_VK,
    Platform.OK: platform_pb2.PLATFORM_OK,
    Platform.MAX: platform_pb2.PLATFORM_MAX,
    Platform.NEWS: platform_pb2.PLATFORM_NEWS,
}
PLATFORM_FROM_PROTO: dict[int, Platform] = {v: k for k, v in PLATFORM_TO_PROTO.items()}


def context_to_proto(request_id: str = "") -> common_pb2.RequestContext:
    """Контекст для вызова соседа. Порты B2 не принимают контекст аргументом: request_id берётся
    из запроса, который запустил поиск (ContextVar наследует и фоновый пайплайн) — B2-12."""
    return common_pb2.RequestContext(request_id=request_id or current_request_id())


def to_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def from_timestamp(value: Timestamp) -> datetime:
    return value.ToDatetime(tzinfo=UTC)


def period_to_proto(period: UtcPeriod) -> platform_pb2.Period:
    return platform_pb2.Period(start=to_timestamp(period.start), end=to_timestamp(period.end))


# Сосед не прислал error-code — выводим его из статуса
STATUS_TO_CODE: dict[grpc.StatusCode, str] = {
    grpc.StatusCode.DEADLINE_EXCEEDED: "TIMEOUT",
    grpc.StatusCode.UNAVAILABLE: "PLATFORM_UNAVAILABLE",
    grpc.StatusCode.UNIMPLEMENTED: "NOT_IMPLEMENTED",
    grpc.StatusCode.RESOURCE_EXHAUSTED: "RATE_LIMITED",
    grpc.StatusCode.INVALID_ARGUMENT: "VALIDATION_ERROR",
    grpc.StatusCode.NOT_FOUND: "SOURCE_NOT_FOUND",
}


def upstream_error(service: str, e: grpc.aio.AioRpcError) -> UpstreamError:
    code = STATUS_TO_CODE.get(e.code(), "UPSTREAM_ERROR")
    for key, value in e.trailing_metadata() or ():
        if key == "error-code":
            code = str(value)
    if e.code() is grpc.StatusCode.DEADLINE_EXCEEDED:
        message = f"{service}: не ответил вовремя"
    elif e.code() is grpc.StatusCode.UNAVAILABLE and code == "PLATFORM_UNAVAILABLE":
        message = e.details() or f"{service}: недоступен"
    else:
        message = e.details() or code
    return UpstreamError(service, code, message)

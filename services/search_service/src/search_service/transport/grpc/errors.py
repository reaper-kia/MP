"""Исключение → gRPC-статус + публичный код (trailing metadata "error-code").

Новая ошибка = одна строка в ERROR_CODES. Ошибки соседей (UpstreamError) пробрасываются с их кодом.
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import grpc

from search_service.applications.exceptions import (
    NotImplementedYetError,
    ResultNotFoundError,
    SearchInvalidParamsError,
    SearchNotFinishedError,
    SearchNotFoundError,
    SourceAlreadyExistsError,
    SourceNotFoundError,
    UpstreamError,
)
from search_service.applications.request_context import bind_request_id
from search_service.domain.exceptions import InvalidPeriodError, InvalidStatusTransitionError

logger = logging.getLogger(__name__)

type Context = grpc.aio.ServicerContext[Any, Any]

ERROR_CODES: list[tuple[type[Exception], grpc.StatusCode, str]] = [
    (SourceNotFoundError, grpc.StatusCode.NOT_FOUND, "SOURCE_NOT_FOUND"),
    (SourceAlreadyExistsError, grpc.StatusCode.ALREADY_EXISTS, "SOURCE_ALREADY_EXISTS"),
    (SearchNotFoundError, grpc.StatusCode.NOT_FOUND, "SEARCH_NOT_FOUND"),
    (SearchInvalidParamsError, grpc.StatusCode.INVALID_ARGUMENT, "SEARCH_INVALID_PARAMS"),
    (InvalidPeriodError, grpc.StatusCode.INVALID_ARGUMENT, "SEARCH_INVALID_PARAMS"),
    (SearchNotFinishedError, grpc.StatusCode.FAILED_PRECONDITION, "SEARCH_NOT_FINISHED"),
    (InvalidStatusTransitionError, grpc.StatusCode.FAILED_PRECONDITION, "INVALID_STATE"),
    (ResultNotFoundError, grpc.StatusCode.NOT_FOUND, "RESULT_NOT_FOUND"),
    (NotImplementedYetError, grpc.StatusCode.UNIMPLEMENTED, "NOT_IMPLEMENTED"),
]

# публичный код соседа → наш статус (код отдаём как есть)
UPSTREAM_STATUS: dict[str, grpc.StatusCode] = {
    "UNSUPPORTED_URL": grpc.StatusCode.INVALID_ARGUMENT,
    "VALIDATION_ERROR": grpc.StatusCode.INVALID_ARGUMENT,
    "SOURCE_NOT_FOUND": grpc.StatusCode.NOT_FOUND,
    "SOURCE_PRIVATE": grpc.StatusCode.FAILED_PRECONDITION,
    "RATE_LIMITED": grpc.StatusCode.RESOURCE_EXHAUSTED,
    "TIMEOUT": grpc.StatusCode.DEADLINE_EXCEEDED,
    "NOT_IMPLEMENTED": grpc.StatusCode.UNIMPLEMENTED,
}


def find_error(error: Exception) -> tuple[grpc.StatusCode, str] | None:
    if isinstance(error, UpstreamError):
        return UPSTREAM_STATUS.get(error.code, grpc.StatusCode.UNAVAILABLE), error.code
    for error_type, status_code, public_code in ERROR_CODES:
        if isinstance(error, error_type):
            return status_code, public_code
    return None


def grpc_errors[S, Req, Resp](
    method: Callable[[S, Req, Context], Awaitable[Resp]],
) -> Callable[[S, Req, Context], Awaitable[Resp]]:
    @wraps(method)
    async def wrapper(self: S, request: Req, context: Context) -> Resp:
        # request_id из gateway — в логи этого запроса и (через ContextVar) в вызовы соседей
        request_id = getattr(getattr(request, "context", None), "request_id", "")
        bind_request_id(request_id if isinstance(request_id, str) else "")
        try:
            return await method(self, request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            found = find_error(e)
            if found is None:
                logger.exception(
                    "Unhandled error in %s (request_id=%s)", method.__name__, request_id
                )
                await context.abort(grpc.StatusCode.INTERNAL, "Internal server error.")
            else:
                status_code, public_code = found
                await context.abort(
                    status_code, str(e), trailing_metadata=(("error-code", public_code),)
                )
            raise

    return wrapper

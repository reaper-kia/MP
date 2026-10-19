"""Исключение → gRPC-статус + публичный код (trailing metadata "error-code").

Новая ошибка = одна строка в ERROR_CODES. Порядок важен: первое совпадение по isinstance.
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import grpc

from collector_service.applications.exceptions import InvalidRequestError, NotImplementedYetError
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
    UnsupportedUrlError,
)

logger = logging.getLogger(__name__)

type Context = grpc.aio.ServicerContext[Any, Any]

ERROR_CODES: list[tuple[type[Exception], grpc.StatusCode, str]] = [
    (InvalidRequestError, grpc.StatusCode.INVALID_ARGUMENT, "VALIDATION_ERROR"),
    (UnsupportedUrlError, grpc.StatusCode.INVALID_ARGUMENT, "UNSUPPORTED_URL"),
    (SourceNotFoundError, grpc.StatusCode.NOT_FOUND, "SOURCE_NOT_FOUND"),
    (SourcePrivateError, grpc.StatusCode.FAILED_PRECONDITION, "SOURCE_PRIVATE"),
    (PlatformUnavailableError, grpc.StatusCode.UNAVAILABLE, "PLATFORM_UNAVAILABLE"),
    (RateLimitedError, grpc.StatusCode.RESOURCE_EXHAUSTED, "RATE_LIMITED"),
    (NotImplementedYetError, grpc.StatusCode.UNIMPLEMENTED, "NOT_IMPLEMENTED"),
]


def find_error(error: Exception) -> tuple[grpc.StatusCode, str] | None:
    for error_type, status_code, public_code in ERROR_CODES:
        if isinstance(error, error_type):
            return status_code, public_code
    return None


def grpc_errors[S, Req, Resp](
    method: Callable[[S, Req, Context], Awaitable[Resp]],
) -> Callable[[S, Req, Context], Awaitable[Resp]]:
    @wraps(method)
    async def wrapper(self: S, request: Req, context: Context) -> Resp:
        try:
            return await method(self, request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            found = find_error(e)
            if found is None:
                logger.exception("Unhandled error in %s", method.__name__)
                await context.abort(grpc.StatusCode.INTERNAL, "Internal server error.")
            else:
                status_code, public_code = found
                await context.abort(
                    status_code, str(e), trailing_metadata=(("error-code", public_code),)
                )
            raise

    return wrapper

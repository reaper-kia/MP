"""Исключение → gRPC-статус + публичный код ошибки.

Код уходит в trailing metadata "error-code", gateway отдаёт его фронту в поле error.code.
Новая ошибка = одна строка в ERROR_CODES.
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import grpc

from example_service.applications.exceptions import (
    ItemNotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)
from example_service.domain.exceptions import InvalidItemTitleError, ItemAlreadyDoneError

logger = logging.getLogger(__name__)

type Context = grpc.aio.ServicerContext[Any, Any]

ERROR_CODES: list[tuple[type[Exception], grpc.StatusCode, str]] = [
    (InvalidItemTitleError, grpc.StatusCode.INVALID_ARGUMENT, "INVALID_TITLE"),
    (ItemAlreadyDoneError, grpc.StatusCode.FAILED_PRECONDITION, "ITEM_IS_DONE"),
    (ItemNotFoundError, grpc.StatusCode.NOT_FOUND, "ITEM_NOT_FOUND"),
    (UnauthenticatedError, grpc.StatusCode.UNAUTHENTICATED, "UNAUTHENTICATED"),
    (PermissionDeniedError, grpc.StatusCode.PERMISSION_DENIED, "PERMISSION_DENIED"),
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

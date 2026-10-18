"""AppError ⇄ gRPC status.

Сервер: декоратор `@rpc` на методе servicer'а — ставит request_id в логи, превращает
AppError в нужный статус и кладёт публичный code/details в trailing metadata.
Клиент: `app_error_from_rpc(exc)` — обратно в AppError (для вызовов сервис → сервис),
`parse_rpc_error(exc)` — сырые поля (их использует Gateway).
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

import grpc
from grpc import aio

from platform_common.context import request_id_var
from platform_common.errors import (
    ERROR_CLASS_BY_KIND,
    AppError,
    ErrorDetail,
    ErrorKind,
)

logger = logging.getLogger(__name__)

type ServicerContext = aio.ServicerContext[Any, Any]

ERROR_CODE_KEY = "x-error-code"
ERROR_DETAILS_KEY = "x-error-details"

STATUS_BY_KIND: dict[ErrorKind, grpc.StatusCode] = {
    ErrorKind.VALIDATION: grpc.StatusCode.INVALID_ARGUMENT,
    ErrorKind.UNAUTHENTICATED: grpc.StatusCode.UNAUTHENTICATED,
    ErrorKind.PERMISSION_DENIED: grpc.StatusCode.PERMISSION_DENIED,
    ErrorKind.NOT_FOUND: grpc.StatusCode.NOT_FOUND,
    ErrorKind.ALREADY_EXISTS: grpc.StatusCode.ALREADY_EXISTS,
    ErrorKind.CONFLICT: grpc.StatusCode.FAILED_PRECONDITION,
    ErrorKind.RATE_LIMITED: grpc.StatusCode.RESOURCE_EXHAUSTED,
    ErrorKind.UNAVAILABLE: grpc.StatusCode.UNAVAILABLE,
    ErrorKind.TIMEOUT: grpc.StatusCode.DEADLINE_EXCEEDED,
    ErrorKind.INTERNAL: grpc.StatusCode.INTERNAL,
}
KIND_BY_STATUS: dict[grpc.StatusCode, ErrorKind] = {v: k for k, v in STATUS_BY_KIND.items()}
KIND_BY_STATUS[grpc.StatusCode.ABORTED] = ErrorKind.CONFLICT


def _set_request_id(request: Any) -> None:
    ctx = getattr(request, "context", None)
    request_id = getattr(ctx, "request_id", "") if ctx is not None else ""
    request_id_var.set(request_id or "-")


def rpc[S, Req, Resp](
    method: Callable[[S, Req, ServicerContext], Awaitable[Resp]],
) -> Callable[[S, Req, ServicerContext], Awaitable[Resp]]:
    """Оборачивает unary-unary метод servicer'а."""

    @wraps(method)
    async def wrapper(self: S, request: Req, context: ServicerContext) -> Resp:
        _set_request_id(request)
        try:
            return await method(self, request, context)
        except aio.AbortError:
            raise
        except AppError as exc:
            status = STATUS_BY_KIND[exc.kind]
            if exc.kind is ErrorKind.INTERNAL:
                logger.exception("%s failed", method.__name__)
            else:
                logger.info("%s -> %s %s", method.__name__, status.name, exc.public_code)
            await context.abort(status, exc.message, trailing_metadata=_metadata(exc))
            raise  # недостижимо: abort бросает AbortError
        except Exception:
            logger.exception("Unhandled error in %s", method.__name__)
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")
            raise

    return wrapper


def _metadata(exc: AppError) -> tuple[tuple[str, str], ...]:
    meta: list[tuple[str, str]] = [(ERROR_CODE_KEY, exc.public_code)]
    if exc.details:
        payload = [{"field": d.field, "reason": d.reason} for d in exc.details]
        meta.append((ERROR_DETAILS_KEY, json.dumps(payload)))
    return tuple(meta)


@dataclass(frozen=True, slots=True)
class RpcErrorInfo:
    status: grpc.StatusCode
    kind: ErrorKind
    code: str | None  # публичный code, если сервер его прислал
    message: str
    details: list[ErrorDetail]


def parse_rpc_error(exc: aio.AioRpcError) -> RpcErrorInfo:
    status = exc.code()
    code: str | None = None
    details: list[ErrorDetail] = []
    for key, value in exc.trailing_metadata() or ():
        if key == ERROR_CODE_KEY:
            code = str(value)
        elif key == ERROR_DETAILS_KEY:
            try:
                details = [ErrorDetail(d["field"], d["reason"]) for d in json.loads(value)]
            except (ValueError, KeyError, TypeError):
                details = []
    kind = KIND_BY_STATUS.get(status, ErrorKind.INTERNAL)
    return RpcErrorInfo(status, kind, code, exc.details() or "", details)


def app_error_from_rpc(exc: aio.AioRpcError) -> AppError:
    """Пробросить ошибку соседнего сервиса как свою (код сохраняется)."""
    info = parse_rpc_error(exc)
    error_cls = ERROR_CLASS_BY_KIND[info.kind]
    return error_cls(info.message, details=info.details, code=info.code)

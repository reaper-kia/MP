"""Единый формат ошибок (docs/api.md):

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": [...]}}

Роутеры НЕ ловят ошибки gRPC: AioRpcError долетает сюда и превращается в HTTP.
"""

import logging
from typing import Any

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from grpc import aio
from starlette.exceptions import HTTPException as StarletteHTTPException

from platform_common.errors import AppError, ErrorDetail, ErrorKind
from platform_common.grpc.errors import parse_rpc_error

logger = logging.getLogger(__name__)

HTTP_BY_KIND: dict[ErrorKind, int] = {
    ErrorKind.VALIDATION: 422,
    ErrorKind.UNAUTHENTICATED: 401,
    ErrorKind.PERMISSION_DENIED: 403,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.ALREADY_EXISTS: 409,
    ErrorKind.CONFLICT: 409,
    ErrorKind.RATE_LIMITED: 429,
    ErrorKind.UNAVAILABLE: 503,
    ErrorKind.TIMEOUT: 504,
    ErrorKind.INTERNAL: 500,
}

DEFAULT_CODE_BY_STATUS: dict[grpc.StatusCode, str] = {
    grpc.StatusCode.INVALID_ARGUMENT: "VALIDATION_ERROR",
    grpc.StatusCode.UNAUTHENTICATED: "UNAUTHENTICATED",
    grpc.StatusCode.PERMISSION_DENIED: "PERMISSION_DENIED",
    grpc.StatusCode.NOT_FOUND: "NOT_FOUND",
    grpc.StatusCode.ALREADY_EXISTS: "ALREADY_EXISTS",
    grpc.StatusCode.FAILED_PRECONDITION: "INVALID_STATE_TRANSITION",
    grpc.StatusCode.ABORTED: "CONCURRENT_MODIFICATION",
    grpc.StatusCode.RESOURCE_EXHAUSTED: "RATE_LIMITED",
    grpc.StatusCode.UNAVAILABLE: "SERVICE_UNAVAILABLE",
    grpc.StatusCode.DEADLINE_EXCEEDED: "UPSTREAM_TIMEOUT",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def rpc_error_to_api(exc: aio.AioRpcError) -> ApiError:
    info = parse_rpc_error(exc)
    if info.status in (
        grpc.StatusCode.INTERNAL,
        grpc.StatusCode.UNKNOWN,
        grpc.StatusCode.DATA_LOSS,
    ):
        return ApiError(502, "UPSTREAM_ERROR", "Upstream service failed")
    if info.status == grpc.StatusCode.UNAVAILABLE:
        return ApiError(503, "SERVICE_UNAVAILABLE", "Service temporarily unavailable")
    if info.status == grpc.StatusCode.DEADLINE_EXCEEDED:
        return ApiError(504, "UPSTREAM_TIMEOUT", "Upstream service timed out")
    code = info.code or DEFAULT_CODE_BY_STATUS.get(info.status, "UPSTREAM_ERROR")
    return ApiError(HTTP_BY_KIND[info.kind], code, info.message, info.details)


def app_error_to_api(exc: AppError) -> ApiError:
    return ApiError(HTTP_BY_KIND[exc.kind], exc.public_code, exc.message, exc.details)


def error_body(request_id: str, err: ApiError) -> dict[str, Any]:
    return {
        "error": {
            "code": err.code,
            "message": err.message,
            "request_id": request_id,
            "details": [{"field": d.field, "reason": d.reason} for d in err.details],
        }
    }


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def error_response(request: Request, err: ApiError) -> JSONResponse:
    rid = _request_id(request)
    return JSONResponse(
        error_body(rid, err), status_code=err.status_code, headers={"X-Request-ID": rid}
    )


def register_error_handlers(app: FastAPI) -> None:
    async def on_api_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(request, exc)

    async def on_app_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        return error_response(request, app_error_to_api(exc))

    async def on_rpc_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, aio.AioRpcError)
        err = rpc_error_to_api(exc)
        level = logging.WARNING if err.status_code >= 500 else logging.INFO
        logger.log(level, "gRPC %s -> HTTP %s %s", exc.code().name, err.status_code, err.code)
        return error_response(request, err)

    async def on_validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        details = [
            ErrorDetail(
                field=".".join(
                    str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")
                ),
                reason=str(e.get("type", "invalid")),
            )
            for e in exc.errors()
        ]
        return error_response(
            request, ApiError(422, "VALIDATION_ERROR", "Request validation failed", details)
        )

    async def on_http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "BAD_REQUEST")
        return error_response(request, ApiError(exc.status_code, code, str(exc.detail)))

    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return error_response(request, ApiError(500, "INTERNAL", "Internal server error"))

    app.add_exception_handler(ApiError, on_api_error)
    app.add_exception_handler(AppError, on_app_error)
    app.add_exception_handler(aio.AioRpcError, on_rpc_error)
    app.add_exception_handler(RequestValidationError, on_validation)
    app.add_exception_handler(StarletteHTTPException, on_http)
    app.add_exception_handler(Exception, on_unhandled)

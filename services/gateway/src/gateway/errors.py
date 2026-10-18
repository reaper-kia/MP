"""Единый формат ошибок для фронта:

    {"error": {"code": "ITEM_NOT_FOUND", "message": "...", "request_id": "...", "details": []}}

Роутеры не ловят ошибки gRPC: AioRpcError долетает сюда и превращается в HTTP.
code берётся из trailing metadata "error-code", которую ставят сервисы (transport/grpc/errors.py).
"""

import logging
from typing import Any

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# gRPC-статус → (HTTP-статус, code по умолчанию, если сервис не прислал свой)
GRPC_TO_HTTP: dict[grpc.StatusCode, tuple[int, str]] = {
    grpc.StatusCode.INVALID_ARGUMENT: (422, "VALIDATION_ERROR"),
    grpc.StatusCode.UNAUTHENTICATED: (401, "UNAUTHENTICATED"),
    grpc.StatusCode.PERMISSION_DENIED: (403, "PERMISSION_DENIED"),
    grpc.StatusCode.NOT_FOUND: (404, "NOT_FOUND"),
    grpc.StatusCode.ALREADY_EXISTS: (409, "ALREADY_EXISTS"),
    grpc.StatusCode.FAILED_PRECONDITION: (409, "INVALID_STATE"),
    grpc.StatusCode.ABORTED: (409, "CONFLICT"),
    grpc.StatusCode.RESOURCE_EXHAUSTED: (429, "RATE_LIMITED"),
    grpc.StatusCode.UNAVAILABLE: (503, "SERVICE_UNAVAILABLE"),
    grpc.StatusCode.DEADLINE_EXCEEDED: (504, "UPSTREAM_TIMEOUT"),
}


class ApiError(Exception):
    """Ошибку можно бросить прямо из роутера: raise ApiError(400, "BAD_REQUEST", "...")."""

    def __init__(
        self, status_code: int, code: str, message: str, details: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def from_grpc_error(e: grpc.aio.AioRpcError) -> ApiError:
    status = e.code()
    if status not in GRPC_TO_HTTP:  # INTERNAL, UNKNOWN и т.п. — детали наружу не отдаём
        return ApiError(502, "UPSTREAM_ERROR", "Upstream service failed")

    http_status, default_code = GRPC_TO_HTTP[status]
    code = default_code
    for key, value in e.trailing_metadata() or ():
        if key == "error-code":
            code = str(value)

    message = e.details() or default_code
    if status in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
        message = "Service temporarily unavailable"
    return ApiError(http_status, code, message)


def error_body(request_id: str, err: ApiError) -> dict[str, Any]:
    return {
        "error": {
            "code": err.code,
            "message": err.message,
            "request_id": request_id,
            "details": err.details,
        }
    }


def error_response(request: Request, err: ApiError) -> JSONResponse:
    request_id = str(getattr(request.state, "request_id", ""))
    return JSONResponse(
        error_body(request_id, err),
        status_code=err.status_code,
        headers={"X-Request-ID": request_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(grpc.aio.AioRpcError)
    async def on_grpc_error(request: Request, exc: grpc.aio.AioRpcError) -> JSONResponse:
        err = from_grpc_error(exc)
        logger.info("gRPC %s -> HTTP %s %s", exc.code().name, err.status_code, err.code)
        return error_response(request, err)

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")),
                "reason": str(e["type"]),
            }
            for e in exc.errors()
        ]
        return error_response(
            request, ApiError(422, "VALIDATION_ERROR", "Request validation failed", details)
        )

    @app.exception_handler(StarletteHTTPException)
    async def on_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "BAD_REQUEST")
        return error_response(request, ApiError(exc.status_code, code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return error_response(request, ApiError(500, "INTERNAL", "Internal server error"))

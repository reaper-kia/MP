from datetime import UTC, datetime
from typing import Any

from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel


class ErrorDetailOut(BaseModel):
    field: str
    reason: str


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetailOut]


class ErrorResponse(BaseModel):
    error: ErrorOut


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


def ts(value: Timestamp) -> datetime:
    return value.ToDatetime(tzinfo=UTC)


def empty_to_none(value: str) -> str | None:
    return value or None


# Для декоратора роутера: какие ошибки показать в OpenAPI
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503, 504)
}

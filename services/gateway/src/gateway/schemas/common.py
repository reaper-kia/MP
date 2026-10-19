from datetime import UTC, datetime
from typing import Any

from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, str]]


class ErrorResponse(BaseModel):
    error: ErrorOut


def ts(value: Timestamp) -> datetime:
    return value.ToDatetime(tzinfo=UTC)


def opt_ts(message: Any, field: str) -> datetime | None:
    """optional Timestamp: не заполнен → None («нет данных»)."""
    return ts(getattr(message, field)) if message.HasField(field) else None


def opt(message: Any, field: str) -> Any:
    """optional-поле proto: не заполнено → None."""
    return getattr(message, field) if message.HasField(field) else None


# какие ошибки показывать в Swagger у каждого роутера
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (404, 409, 422, 429, 501, 502, 503, 504)
}

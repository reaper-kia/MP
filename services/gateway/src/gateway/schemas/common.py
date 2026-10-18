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


# какие ошибки показывать в Swagger у каждого роутера
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
}

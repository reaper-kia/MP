"""Иерархия ошибок приложения.

Доменные/прикладные ошибки наследуются от одного из базовых классов ниже и задают свой
публичный `code`. Транспорт сам превратит их в gRPC-статус (grpc/errors.py), а Gateway —
в HTTP-ответ единого формата. Никаких try/except в servicer'ах и роутерах не нужно.

    class ItemNotFound(NotFoundError):
        code = "ITEM_NOT_FOUND"
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class ErrorKind(StrEnum):
    VALIDATION = "validation"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    field: str
    reason: str


class AppError(Exception):
    kind: ClassVar[ErrorKind] = ErrorKind.INTERNAL
    code: ClassVar[str] = "INTERNAL"
    default_message: ClassVar[str] = "Internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or []
        # code можно переопределить на экземпляре (нужно при пробросе ошибок между сервисами)
        self.public_code = code or type(self).code
        super().__init__(self.message)


class ValidationError(AppError):
    kind = ErrorKind.VALIDATION
    code = "VALIDATION_ERROR"
    default_message = "Validation failed"

    @classmethod
    def field(cls, field: str, reason: str, message: str | None = None) -> "ValidationError":
        return cls(message or f"Invalid field: {field}", details=[ErrorDetail(field, reason)])


class UnauthenticatedError(AppError):
    kind = ErrorKind.UNAUTHENTICATED
    code = "UNAUTHENTICATED"
    default_message = "Authentication required"


class PermissionDeniedError(AppError):
    kind = ErrorKind.PERMISSION_DENIED
    code = "PERMISSION_DENIED"
    default_message = "Permission denied"


class NotFoundError(AppError):
    kind = ErrorKind.NOT_FOUND
    code = "NOT_FOUND"
    default_message = "Not found"


class AlreadyExistsError(AppError):
    kind = ErrorKind.ALREADY_EXISTS
    code = "ALREADY_EXISTS"
    default_message = "Already exists"


class ConflictError(AppError):
    """Операция невозможна в текущем состоянии (FAILED_PRECONDITION → 409)."""

    kind = ErrorKind.CONFLICT
    code = "INVALID_STATE_TRANSITION"
    default_message = "Operation is not allowed in the current state"


class RateLimitedError(AppError):
    kind = ErrorKind.RATE_LIMITED
    code = "RATE_LIMITED"
    default_message = "Too many requests"


class UnavailableError(AppError):
    kind = ErrorKind.UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    default_message = "Service temporarily unavailable"


class UpstreamTimeoutError(AppError):
    kind = ErrorKind.TIMEOUT
    code = "UPSTREAM_TIMEOUT"
    default_message = "Upstream service timed out"


ERROR_CLASS_BY_KIND: dict[ErrorKind, type[AppError]] = {
    ErrorKind.VALIDATION: ValidationError,
    ErrorKind.UNAUTHENTICATED: UnauthenticatedError,
    ErrorKind.PERMISSION_DENIED: PermissionDeniedError,
    ErrorKind.NOT_FOUND: NotFoundError,
    ErrorKind.ALREADY_EXISTS: AlreadyExistsError,
    ErrorKind.CONFLICT: ConflictError,
    ErrorKind.RATE_LIMITED: RateLimitedError,
    ErrorKind.UNAVAILABLE: UnavailableError,
    ErrorKind.TIMEOUT: UpstreamTimeoutError,
    ErrorKind.INTERNAL: AppError,
}

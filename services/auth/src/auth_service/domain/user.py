import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from auth_service.domain.errors import InvalidEmailError, InvalidNameError, WeakPasswordError
from platform_common.errors import ErrorDetail
from platform_common.time import utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise InvalidEmailError(details=[ErrorDetail("email", "invalid_format")])
    return email


def validate_password(raw: str) -> None:
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(details=[ErrorDetail("password", "too_short")])


def normalize_name(raw: str) -> str:
    name = raw.strip()
    if not 1 <= len(name) <= 64:
        raise InvalidNameError(details=[ErrorDetail("name", "invalid_length")])
    return name


@dataclass
class User:
    id: UUID
    email: str
    name: str
    password_hash: str
    role: Role
    created_at: datetime

    @classmethod
    def register(cls, *, email: str, name: str, password_hash: str, role: Role) -> "User":
        return cls(
            id=uuid4(),
            email=normalize_email(email),
            name=normalize_name(name),
            password_hash=password_hash,
            role=role,
            created_at=utcnow(),
        )

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from auth_service.domain.value_objects import Email, UserName


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(slots=True, kw_only=True)
class User:
    email: Email
    name: UserName
    password_hash: str

    id: UUID = field(default_factory=uuid4)
    role: UserRole = UserRole.USER
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def register(
        cls, email: Email, name: UserName, password_hash: str, role: UserRole = UserRole.USER
    ) -> "User":
        return cls(email=email, name=name, password_hash=password_hash, role=role)


@dataclass(slots=True, kw_only=True)
class RefreshSession:
    """Refresh-токен хранится только в виде хэша."""

    user_id: UUID
    token_hash: str
    expires_at: datetime

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)
    revoked_at: datetime | None = None

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = utc_now()

    def is_active(self, now: datetime | None = None) -> bool:
        return self.revoked_at is None and self.expires_at > (now or utc_now())

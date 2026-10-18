from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from auth_service.domain.user import Role, User


@dataclass(frozen=True, slots=True)
class UserView:
    id: UUID
    email: str
    name: str
    role: Role
    created_at: datetime

    @classmethod
    def from_user(cls, user: User, *, hide_email: bool = False) -> "UserView":
        return cls(
            id=user.id,
            email="" if hide_email else user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at,
        )


@dataclass(frozen=True, slots=True)
class Tokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: UserView
    tokens: Tokens

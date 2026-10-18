from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from auth_service.domain.entities import User


@dataclass(frozen=True, slots=True)
class UserReadModel:
    id: UUID
    email: str
    name: str
    role: str
    created_at: datetime

    @classmethod
    def from_user(cls, user: User, *, hide_email: bool = False) -> "UserReadModel":
        return cls(
            id=user.id,
            email="" if hide_email else user.email.value,
            name=user.name.value,
            role=user.role.value,
            created_at=user.created_at,
        )

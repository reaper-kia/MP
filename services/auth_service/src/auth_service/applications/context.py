from dataclasses import dataclass
from uuid import UUID

from auth_service.applications.exceptions import PermissionDeniedError, UnauthenticatedError


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Кто делает запрос. Заполняет Gateway после проверки JWT."""

    request_id: str
    actor_user_id: UUID | None = None
    actor_role: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.actor_role == "admin"

    def require_user(self) -> UUID:
        if self.actor_user_id is None:
            raise UnauthenticatedError("Authentication required")
        return self.actor_user_id

    def require_owner_or_admin(self, owner_id: UUID) -> UUID:
        user_id = self.require_user()
        if user_id != owner_id and not self.is_admin:
            raise PermissionDeniedError("Permission denied")
        return user_id

"""RequestContext внутри сервиса + contextvar с request_id для логов."""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID, uuid4

from contracts.common.v1 import common_pb2
from platform_common.errors import PermissionDeniedError, UnauthenticatedError

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

ROLE_USER = "user"
ROLE_ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    actor_user_id: UUID | None = None
    actor_role: str | None = None

    @classmethod
    def from_proto(cls, msg: common_pb2.RequestContext) -> "RequestContext":
        actor: UUID | None = None
        if msg.actor_user_id:
            try:
                actor = UUID(msg.actor_user_id)
            except ValueError as exc:
                raise UnauthenticatedError("Malformed actor id in request context") from exc
        return cls(
            request_id=msg.request_id or str(uuid4()),
            actor_user_id=actor,
            actor_role=msg.actor_role or None,
        )

    @classmethod
    def system(cls) -> "RequestContext":
        """Контекст для фоновых задач/consumer'ов."""
        return cls(request_id=str(uuid4()), actor_role="system")

    def to_proto(self) -> common_pb2.RequestContext:
        """Для вызовов сервис → сервис: прокидываем тот же контекст дальше."""
        return common_pb2.RequestContext(
            request_id=self.request_id,
            actor_user_id=str(self.actor_user_id) if self.actor_user_id else "",
            actor_role=self.actor_role or "",
        )

    @property
    def is_authenticated(self) -> bool:
        return self.actor_user_id is not None

    @property
    def is_admin(self) -> bool:
        return self.actor_role == ROLE_ADMIN

    def require_user(self) -> UUID:
        if self.actor_user_id is None:
            raise UnauthenticatedError()
        return self.actor_user_id

    def require_role(self, *roles: str) -> UUID:
        user_id = self.require_user()
        if self.actor_role not in roles:
            raise PermissionDeniedError()
        return user_id

    def require_owner_or_admin(self, owner_id: UUID) -> UUID:
        user_id = self.require_user()
        if user_id != owner_id and not self.is_admin:
            raise PermissionDeniedError()
        return user_id

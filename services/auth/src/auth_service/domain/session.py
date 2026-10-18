from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from platform_common.time import utcnow


@dataclass
class RefreshSession:
    """Refresh-токен хранится только в виде хэша; сам токен знает лишь клиент."""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def start(cls, user_id: UUID, token_hash: str, ttl: timedelta) -> "RefreshSession":
        return cls(id=uuid4(), user_id=user_id, token_hash=token_hash, expires_at=utcnow() + ttl)

    def is_active(self, now: datetime | None = None) -> bool:
        return self.revoked_at is None and (now or utcnow()) < self.expires_at

    def revoke(self, now: datetime | None = None) -> None:
        if self.revoked_at is None:
            self.revoked_at = now or utcnow()

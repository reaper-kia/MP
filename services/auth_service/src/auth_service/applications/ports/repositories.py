from typing import Protocol
from uuid import UUID

from auth_service.domain.entities import RefreshSession, User
from auth_service.domain.value_objects import Email


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: Email) -> User | None: ...


class RefreshSessionRepository(Protocol):
    async def add(self, session: RefreshSession) -> None: ...

    async def save(self, session: RefreshSession) -> None: ...

    async def get_by_token_hash_for_update(self, token_hash: str) -> RefreshSession | None: ...

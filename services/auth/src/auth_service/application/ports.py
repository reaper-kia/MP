"""Порты (интерфейсы), которые нужны use case'ам. Реализации — в infra/."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from auth_service.domain.session import RefreshSession
from auth_service.domain.user import User
from platform_common.db.uow import UnitOfWork


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def add(self, user: User) -> None: ...


class SessionRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None: ...
    async def add(self, session: RefreshSession) -> None: ...
    async def update(self, session: RefreshSession) -> None: ...


class EventOutbox(Protocol):
    def add(
        self, topic: str, event_type: str, payload: dict[str, Any], *, key: str | None = None
    ) -> Any: ...


class AuthUnitOfWork(UnitOfWork, Protocol):
    # read-only property в протоколе — чтобы реализация могла иметь более точный тип
    @property
    def users(self) -> UserRepository: ...
    @property
    def sessions(self) -> SessionRepository: ...
    @property
    def outbox(self) -> EventOutbox: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AuthUnitOfWork: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_at: datetime


class TokenService(Protocol):
    def issue_access(self, user_id: UUID, role: str) -> AccessToken: ...
    def new_refresh_token(self) -> str: ...
    def hash_refresh_token(self, token: str) -> str: ...

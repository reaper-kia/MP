"""In-memory реализации портов: хэндлеры тестируются без БД."""

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from auth_service.applications.ports.token_service import IssuedAccessToken
from auth_service.domain.entities import RefreshSession, User
from auth_service.domain.value_objects import Email


class FakeDb:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.sessions: dict[UUID, RefreshSession] = {}


class FakeUserRepository:
    def __init__(self, db: FakeDb) -> None:
        self._db = db

    async def add(self, user: User) -> None:
        self._db.users[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._db.users.get(user_id)

    async def get_by_email(self, email: Email) -> User | None:
        return next((u for u in self._db.users.values() if u.email == email), None)


class FakeRefreshSessionRepository:
    def __init__(self, db: FakeDb) -> None:
        self._db = db

    async def add(self, session: RefreshSession) -> None:
        self._db.sessions[session.id] = replace(session)

    async def save(self, session: RefreshSession) -> None:
        self._db.sessions[session.id] = replace(session)

    async def get_by_token_hash_for_update(self, token_hash: str) -> RefreshSession | None:
        for s in self._db.sessions.values():
            if s.token_hash == token_hash:
                return replace(s)
        return None


class FakeUnitOfWork:
    """Упрощённо: пишет сразу в FakeDb, commit только отмечается."""

    def __init__(self, db: FakeDb) -> None:
        self.users = FakeUserRepository(db)
        self.refresh_sessions = FakeRefreshSessionRepository(db)
        self.committed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class FakePasswordHasher:
    async def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    async def verify(self, raw_password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{raw_password}"


class FakeAccessTokenIssuer:
    def issue(self, user_id: UUID, role: str, now: datetime) -> IssuedAccessToken:
        return IssuedAccessToken(
            value=f"access:{user_id}:{role}", expires_at=now + timedelta(minutes=5)
        )


class FakeRefreshTokenService:
    def generate(self) -> str:
        return f"refresh:{uuid4()}"

    def hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

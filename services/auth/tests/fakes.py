"""In-memory реализации портов: use case'ы тестируются без БД и сети."""

import hashlib
from dataclasses import replace
from datetime import timedelta
from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

from auth_service.application.ports import AccessToken
from auth_service.domain.errors import EmailTakenError
from auth_service.domain.session import RefreshSession
from auth_service.domain.user import User
from platform_common.time import utcnow


class FakeDb:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.sessions: dict[UUID, RefreshSession] = {}
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self.commits = 0


class FakeUsers:
    def __init__(self, db: FakeDb, staged: dict[UUID, User]) -> None:
        self._db, self._staged = db, staged

    async def get(self, user_id: UUID) -> User | None:
        return self._staged.get(user_id) or self._db.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        all_users = {**self._db.users, **self._staged}.values()
        return next((u for u in all_users if u.email == email), None)

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email):
            raise EmailTakenError()
        self._staged[user.id] = user


class FakeSessions:
    def __init__(self, db: FakeDb, staged: dict[UUID, RefreshSession]) -> None:
        self._db, self._staged = db, staged

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        for s in {**self._db.sessions, **self._staged}.values():
            if s.token_hash == token_hash:
                return replace(s)
        return None

    async def add(self, session: RefreshSession) -> None:
        self._staged[session.id] = replace(session)

    async def update(self, session: RefreshSession) -> None:
        self._staged[session.id] = replace(session)


class FakeOutbox:
    def __init__(self, staged: list[tuple[str, str, dict[str, Any]]]) -> None:
        self._staged = staged

    def add(
        self, topic: str, event_type: str, payload: dict[str, Any], *, key: str | None = None
    ) -> None:
        self._staged.append((topic, event_type, payload))


class FakeUnitOfWork:
    def __init__(self, db: FakeDb) -> None:
        self._db = db
        self._users: dict[UUID, User] = {}
        self._sessions: dict[UUID, RefreshSession] = {}
        self._events: list[tuple[str, str, dict[str, Any]]] = []
        self.users = FakeUsers(db, self._users)
        self.sessions = FakeSessions(db, self._sessions)
        self.outbox = FakeOutbox(self._events)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.rollback()

    async def commit(self) -> None:
        self._db.users.update(self._users)
        self._db.sessions.update(self._sessions)
        self._db.events.extend(self._events)
        self._db.commits += 1
        await self.rollback()

    async def rollback(self) -> None:
        self._users.clear()
        self._sessions.clear()
        self._events.clear()


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeTokens:
    def issue_access(self, user_id: UUID, role: str) -> AccessToken:
        return AccessToken(
            token=f"access:{user_id}:{role}", expires_at=utcnow() + timedelta(minutes=5)
        )

    def new_refresh_token(self) -> str:
        return f"refresh:{uuid4()}"

    def hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

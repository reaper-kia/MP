from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import EmailTakenError
from auth_service.domain.session import RefreshSession
from auth_service.domain.user import Role, User
from auth_service.infra.db.models import RefreshSessionModel, UserModel


def _user(m: UserModel) -> User:
    return User(
        id=m.id,
        email=m.email,
        name=m.name,
        password_hash=m.password_hash,
        role=Role(m.role),
        created_at=m.created_at,
    )


def _session(m: RefreshSessionModel) -> RefreshSession:
    return RefreshSession(
        id=m.id,
        user_id=m.user_id,
        token_hash=m.token_hash,
        expires_at=m.expires_at,
        revoked_at=m.revoked_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: UUID) -> User | None:
        m = await self._s.get(UserModel, user_id)
        return _user(m) if m else None

    async def get_by_email(self, email: str) -> User | None:
        m = await self._s.scalar(select(UserModel).where(UserModel.email == email))
        return _user(m) if m else None

    async def add(self, user: User) -> None:
        self._s.add(
            UserModel(
                id=user.id,
                email=user.email,
                name=user.name,
                password_hash=user.password_hash,
                role=user.role.value,
                created_at=user.created_at,
            )
        )
        try:
            await self._s.flush()
        except IntegrityError as exc:  # гонка двух регистраций с одним email
            raise EmailTakenError() from exc


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        m = await self._s.scalar(
            select(RefreshSessionModel)
            .where(RefreshSessionModel.token_hash == token_hash)
            .with_for_update()
        )
        return _session(m) if m else None

    async def add(self, session: RefreshSession) -> None:
        self._s.add(
            RefreshSessionModel(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._s.flush()

    async def update(self, session: RefreshSession) -> None:
        await self._s.execute(
            update(RefreshSessionModel)
            .where(RefreshSessionModel.id == session.id)
            .values(revoked_at=session.revoked_at, expires_at=session.expires_at)
        )

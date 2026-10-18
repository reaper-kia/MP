from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.applications.ports.repositories import UserRepository
from auth_service.domain.entities import User, UserRole
from auth_service.domain.exceptions import UserAlreadyRegisterError
from auth_service.domain.value_objects import Email, UserName
from auth_service.infra.database.models import UserModel


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(self._to_model(user))
        try:
            await self._session.flush()
        except IntegrityError as exc:  # две регистрации с одним email одновременно
            raise UserAlreadyRegisterError("Email already registered") from exc

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: Email) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.value)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    @staticmethod
    def _to_model(user: User) -> UserModel:
        return UserModel(
            id=user.id,
            email=user.email.value,
            name=user.name.value,
            password_hash=user.password_hash,
            role=user.role.value,
            created_at=user.created_at,
        )

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            email=Email(model.email),
            name=UserName(model.name),
            password_hash=model.password_hash,
            role=UserRole(model.role),
            created_at=model.created_at,
        )

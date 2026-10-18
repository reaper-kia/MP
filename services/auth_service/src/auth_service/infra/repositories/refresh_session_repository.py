from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.applications.ports.repositories import RefreshSessionRepository
from auth_service.domain.entities import RefreshSession
from auth_service.infra.database.models import RefreshSessionModel


class SQLAlchemyRefreshSessionRepository(RefreshSessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: RefreshSession) -> None:
        self._session.add(
            RefreshSessionModel(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                expires_at=session.expires_at,
                created_at=session.created_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._session.flush()

    async def save(self, session: RefreshSession) -> None:
        model = await self._session.get(RefreshSessionModel, session.id)
        if model is not None:
            model.revoked_at = session.revoked_at
            model.expires_at = session.expires_at

    async def get_by_token_hash_for_update(self, token_hash: str) -> RefreshSession | None:
        stmt = (
            select(RefreshSessionModel)
            .where(RefreshSessionModel.token_hash == token_hash)
            .with_for_update()
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        return RefreshSession(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            created_at=model.created_at,
            revoked_at=model.revoked_at,
        )

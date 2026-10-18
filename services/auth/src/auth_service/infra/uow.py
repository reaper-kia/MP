from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.infra.db.models import OutboxMessage
from auth_service.infra.db.repositories import (
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from platform_common.db.uow import BaseSqlAlchemyUnitOfWork
from platform_common.kafka.outbox import OutboxWriter


class SqlAlchemyAuthUnitOfWork(BaseSqlAlchemyUnitOfWork):
    users: SqlAlchemyUserRepository
    sessions: SqlAlchemySessionRepository
    outbox: OutboxWriter

    def _init_repositories(self, session: AsyncSession) -> None:
        self.users = SqlAlchemyUserRepository(session)
        self.sessions = SqlAlchemySessionRepository(session)
        self.outbox = OutboxWriter(session, OutboxMessage, producer="auth")

from sqlalchemy.ext.asyncio import AsyncSession

from example_service.infra.db.models import OutboxMessage
from example_service.infra.db.repositories import SqlAlchemyItemRepository
from platform_common.db.uow import BaseSqlAlchemyUnitOfWork
from platform_common.kafka.outbox import OutboxWriter


class SqlAlchemyExampleUnitOfWork(BaseSqlAlchemyUnitOfWork):
    items: SqlAlchemyItemRepository
    outbox: OutboxWriter

    def _init_repositories(self, session: AsyncSession) -> None:
        self.items = SqlAlchemyItemRepository(session)
        self.outbox = OutboxWriter(session, OutboxMessage, producer="example")

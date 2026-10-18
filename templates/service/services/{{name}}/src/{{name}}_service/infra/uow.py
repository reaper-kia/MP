from platform_common.db.uow import BaseSqlAlchemyUnitOfWork
from platform_common.kafka.outbox import OutboxWriter
from sqlalchemy.ext.asyncio import AsyncSession

from {{name}}_service.infra.db.models import OutboxMessage
from {{name}}_service.infra.db.repositories import SqlAlchemy{{Entity}}Repository


class SqlAlchemy{{Name}}UnitOfWork(BaseSqlAlchemyUnitOfWork):
    {{entities}}: SqlAlchemy{{Entity}}Repository
    outbox: OutboxWriter

    def _init_repositories(self, session: AsyncSession) -> None:
        self.{{entities}} = SqlAlchemy{{Entity}}Repository(session)
        self.outbox = OutboxWriter(session, OutboxMessage, producer="{{name}}")

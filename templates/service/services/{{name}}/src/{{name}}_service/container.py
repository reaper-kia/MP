from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from grpc import aio
from platform_common.db.engine import create_engine, create_session_factory
from platform_common.kafka.outbox import OutboxRelay
from platform_common.kafka.producer import KafkaPublisher
from platform_common.mediator import Mediator
from sqlalchemy.ext.asyncio import AsyncEngine

from {{name}}_service.application.commands import Create{{Entity}}, Create{{Entity}}Handler
from {{name}}_service.application.ports import UnitOfWorkFactory
from {{name}}_service.application.queries import (
    Get{{Entity}},
    Get{{Entity}}Handler,
    List{{Entities}},
    List{{Entities}}Handler,
)
from {{name}}_service.config import Settings
from {{name}}_service.infra.db.models import OutboxMessage
from {{name}}_service.infra.uow import SqlAlchemy{{Name}}UnitOfWork


@dataclass
class Container:
    engine: AsyncEngine
    mediator: Mediator
    channels: list[aio.Channel] = field(default_factory=list)
    background: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def close(self) -> None:
        for channel in self.channels:
            await channel.close()
        await self.engine.dispose()


def build_mediator(uow_factory: UnitOfWorkFactory) -> Mediator:
    mediator = Mediator()
    mediator.register(Create{{Entity}}, Create{{Entity}}Handler(uow_factory))
    mediator.register(Get{{Entity}}, Get{{Entity}}Handler(uow_factory))
    mediator.register(List{{Entities}}, List{{Entities}}Handler(uow_factory))
    return mediator


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url, echo=settings.database_echo)
    session_factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemy{{Name}}UnitOfWork:
        return SqlAlchemy{{Name}}UnitOfWork(session_factory)

    # Вызов другого сервиса: channel = create_channel(settings.auth_grpc_target),
    # stub = auth_pb2_grpc.AuthServiceStub(channel), channel → в Container.channels.
    # Пример: services/example/src/example_service/infra/auth_client.py

    container = Container(engine=engine, mediator=build_mediator(uow_factory))
    if settings.kafka_enabled:
        publisher = KafkaPublisher(settings.kafka_bootstrap_servers)
        container.background.append(OutboxRelay(session_factory, OutboxMessage, publisher).run)
    return container

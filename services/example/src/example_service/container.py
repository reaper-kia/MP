from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from grpc import aio
from sqlalchemy.ext.asyncio import AsyncEngine

from example_service.application.commands.items import (
    CreateItem,
    CreateItemHandler,
    DeleteItem,
    DeleteItemHandler,
    UpdateItem,
    UpdateItemHandler,
)
from example_service.application.ports import UnitOfWorkFactory, UserDirectory
from example_service.application.queries.items import (
    GetItem,
    GetItemHandler,
    ListItems,
    ListItemsHandler,
)
from example_service.config import Settings
from example_service.infra.auth_client import GrpcUserDirectory
from example_service.infra.db.models import OutboxMessage, ProcessedEvent
from example_service.infra.uow import SqlAlchemyExampleUnitOfWork
from example_service.transport.kafka.handlers import HANDLERS, TOPICS
from platform_common.db.engine import create_engine, create_session_factory
from platform_common.grpc.client import create_channel
from platform_common.kafka.consumer import KafkaEventConsumer
from platform_common.kafka.outbox import OutboxRelay
from platform_common.kafka.producer import KafkaPublisher
from platform_common.mediator import Mediator


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


def build_mediator(uow_factory: UnitOfWorkFactory, users: UserDirectory) -> Mediator:
    mediator = Mediator()
    mediator.register(CreateItem, CreateItemHandler(uow_factory))
    mediator.register(UpdateItem, UpdateItemHandler(uow_factory))
    mediator.register(DeleteItem, DeleteItemHandler(uow_factory))
    mediator.register(GetItem, GetItemHandler(uow_factory, users))
    mediator.register(ListItems, ListItemsHandler(uow_factory))
    return mediator


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url, echo=settings.database_echo)
    session_factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemyExampleUnitOfWork:
        return SqlAlchemyExampleUnitOfWork(session_factory)

    auth_channel = create_channel(settings.auth_grpc_target, timeout=settings.grpc_client_timeout)
    mediator = build_mediator(uow_factory, GrpcUserDirectory(auth_channel))
    container = Container(engine=engine, mediator=mediator, channels=[auth_channel])

    if settings.kafka_enabled:
        publisher = KafkaPublisher(settings.kafka_bootstrap_servers)
        container.background.append(OutboxRelay(session_factory, OutboxMessage, publisher).run)
        consumer = KafkaEventConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.service_name,
            topics=TOPICS,
            handlers=HANDLERS,
            session_factory=session_factory,
            processed_model=ProcessedEvent,
        )
        container.background.append(consumer.run)
    return container

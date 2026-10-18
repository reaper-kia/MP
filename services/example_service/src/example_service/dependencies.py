"""Composition root: здесь реализации связываются с портами и хэндлеры — с командами."""

from dataclasses import dataclass

import grpc
from sqlalchemy.ext.asyncio import AsyncEngine

from example_service.applications.commands.create_item import CreateItemCommand
from example_service.applications.commands.delete_item import DeleteItemCommand
from example_service.applications.commands.update_item import UpdateItemCommand
from example_service.applications.handlers.create_item import CreateItemCommandHandler
from example_service.applications.handlers.delete_item import DeleteItemCommandHandler
from example_service.applications.handlers.get_item import GetItemQueryHandler
from example_service.applications.handlers.list_items import ListItemsQueryHandler
from example_service.applications.handlers.update_item import UpdateItemCommandHandler
from example_service.applications.mediator import Mediator
from example_service.applications.ports.unit_of_work import UnitOfWorkFactory
from example_service.applications.ports.user_directory import UserDirectory
from example_service.applications.queries.get_item import GetItemQuery
from example_service.applications.queries.list_items import ListItemsQuery
from example_service.infra.clients.auth_client import GrpcUserDirectory
from example_service.infra.config import Settings
from example_service.infra.database.database import create_engine, create_session_factory
from example_service.infra.uow.sqlalchemy_unit_of_work import SQLAlchemyUnitOfWorkFactory


@dataclass(frozen=True)
class Container:
    engine: AsyncEngine
    auth_channel: grpc.aio.Channel
    mediator: Mediator

    async def close(self) -> None:
        await self.auth_channel.close()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings)
    uow_factory = SQLAlchemyUnitOfWorkFactory(create_session_factory(engine))

    # канал к auth_service; соединение установится при первом вызове
    auth_channel = grpc.aio.insecure_channel(settings.auth_grpc_target)
    users = GrpcUserDirectory(auth_channel, timeout=settings.grpc_client_timeout)

    return Container(
        engine=engine,
        auth_channel=auth_channel,
        mediator=build_mediator(uow_factory, users),
    )


def build_mediator(uow_factory: UnitOfWorkFactory, users: UserDirectory) -> Mediator:
    """Единственное место, где сценарии привязываются к командам."""
    mediator = Mediator()
    mediator.register(CreateItemCommand, CreateItemCommandHandler(uow_factory=uow_factory))
    mediator.register(UpdateItemCommand, UpdateItemCommandHandler(uow_factory=uow_factory))
    mediator.register(DeleteItemCommand, DeleteItemCommandHandler(uow_factory=uow_factory))
    mediator.register(GetItemQuery, GetItemQueryHandler(uow_factory=uow_factory, users=users))
    mediator.register(ListItemsQuery, ListItemsQueryHandler(uow_factory=uow_factory))
    return mediator

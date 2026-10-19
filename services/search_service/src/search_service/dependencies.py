"""Composition root: каналы к соседям, клиенты, UoW и регистрация хэндлеров."""

from dataclasses import dataclass

import grpc
from sqlalchemy.ext.asyncio import AsyncEngine

from search_service.applications.commands.results import SetExcludedCommand
from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.commands.sources import (
    CreateSourceCommand,
    DeleteSourceCommand,
    ImportSourcesCommand,
    UpdateSourceCommand,
)
from search_service.applications.handlers.export import ExportSearchQueryHandler
from search_service.applications.handlers.results import (
    ListGroupsQueryHandler,
    ListResultsQueryHandler,
    SetExcludedCommandHandler,
)
from search_service.applications.handlers.searches import (
    CancelSearchCommandHandler,
    GetSearchQueryHandler,
    ListSearchesQueryHandler,
    RetrySearchCommandHandler,
    StartSearchCommandHandler,
)
from search_service.applications.handlers.sources import (
    CreateSourceCommandHandler,
    DeleteSourceCommandHandler,
    ImportSourcesCommandHandler,
    ListSourcesQueryHandler,
    ResolveSourceQueryHandler,
    UpdateSourceCommandHandler,
)
from search_service.applications.mediator import Mediator
from search_service.applications.ports.collector import CollectorClient
from search_service.applications.ports.ml import MlClient
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.queries.results import (
    ExportSearchQuery,
    ListGroupsQuery,
    ListResultsQuery,
)
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.queries.sources import ListSourcesQuery, ResolveSourceQuery
from search_service.infra.clients.collector_client import GrpcCollectorClient
from search_service.infra.clients.ml_client import GrpcMlClient
from search_service.infra.config import Settings
from search_service.infra.database.database import create_engine, create_session_factory
from search_service.infra.uow.sqlalchemy_unit_of_work import SQLAlchemyUnitOfWorkFactory


@dataclass(frozen=True)
class Container:
    engine: AsyncEngine
    collector_channel: grpc.aio.Channel
    ml_channel: grpc.aio.Channel
    mediator: Mediator

    async def close(self) -> None:
        await self.collector_channel.close()
        await self.ml_channel.close()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings)
    uow_factory = SQLAlchemyUnitOfWorkFactory(create_session_factory(engine))

    # каналы к соседям; соединение установится при первом вызове
    collector_channel = grpc.aio.insecure_channel(settings.collector_grpc_target)
    ml_channel = grpc.aio.insecure_channel(settings.ml_grpc_target)
    collector = GrpcCollectorClient(
        collector_channel,
        resolve_timeout=settings.collector_resolve_timeout,
        collect_timeout=settings.collector_collect_timeout,
    )
    ml = GrpcMlClient(
        ml_channel,
        analyze_timeout=settings.ml_analyze_timeout,
        score_timeout=settings.ml_score_timeout,
        group_timeout=settings.ml_group_timeout,
    )
    return Container(
        engine=engine,
        collector_channel=collector_channel,
        ml_channel=ml_channel,
        mediator=build_mediator(uow_factory, collector, ml),
    )


def build_mediator(
    uow_factory: UnitOfWorkFactory, collector: CollectorClient, ml: MlClient
) -> Mediator:
    """Единственное место, где сценарии привязываются к командам."""
    m = Mediator()
    # источники
    m.register(ResolveSourceQuery, ResolveSourceQueryHandler(uow_factory, collector))
    m.register(CreateSourceCommand, CreateSourceCommandHandler(uow_factory, collector))
    m.register(ListSourcesQuery, ListSourcesQueryHandler(uow_factory))
    m.register(UpdateSourceCommand, UpdateSourceCommandHandler(uow_factory))
    m.register(DeleteSourceCommand, DeleteSourceCommandHandler(uow_factory))
    m.register(ImportSourcesCommand, ImportSourcesCommandHandler(uow_factory, collector))
    # поиск
    m.register(StartSearchCommand, StartSearchCommandHandler(uow_factory, collector, ml))
    m.register(GetSearchQuery, GetSearchQueryHandler(uow_factory))
    m.register(ListSearchesQuery, ListSearchesQueryHandler(uow_factory))
    m.register(RetrySearchCommand, RetrySearchCommandHandler(uow_factory))
    m.register(CancelSearchCommand, CancelSearchCommandHandler(uow_factory))
    # подборка
    m.register(ListResultsQuery, ListResultsQueryHandler(uow_factory))
    m.register(ListGroupsQuery, ListGroupsQueryHandler(uow_factory))
    m.register(SetExcludedCommand, SetExcludedCommandHandler(uow_factory))
    m.register(ExportSearchQuery, ExportSearchQueryHandler(uow_factory))
    return m

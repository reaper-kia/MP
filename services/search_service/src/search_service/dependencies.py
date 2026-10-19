"""Composition root: БД, клиенты соседей (gRPC или stub), пайплайн, регистрация хэндлеров.

- UnitOfWork (infra/database/uow.py) один на сервис: каждый `async with uow:` открывает свою
  сессию (ContextVar), поэтому его можно делить между параллельными задачами пайплайна.
- SearchRunner — реестр asyncio.Task по search_id; на старте сервиса все RUNNING/QUEUED поиски
  помечаются FAILED с warning «прерван перезапуском» (mark_interrupted_searches).
"""

import asyncio
import logging
from dataclasses import dataclass, field

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
from search_service.applications.handlers.pipeline import Pipeline
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
from search_service.applications.ports.collector_client import CollectorClient
from search_service.applications.ports.ml_client import MlClient
from search_service.applications.ports.runner import SearchRunner
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.results import (
    ExportSearchQuery,
    ListGroupsQuery,
    ListResultsQuery,
)
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.queries.sources import ListSourcesQuery, ResolveSourceQuery
from search_service.domain.entities import utcnow
from search_service.domain.enums import SearchStage, SearchStatus
from search_service.infra.clients.collector_client import GrpcCollectorClient
from search_service.infra.clients.ml_client import GrpcMlClient
from search_service.infra.collector_stub import StubCollectorClient
from search_service.infra.config import Settings
from search_service.infra.database.database import create_engine, create_session_factory
from search_service.infra.database.uow import UnitOfWork as SqlAlchemyUnitOfWork
from search_service.infra.ml_client import StubMl
from search_service.infra.runner import SearchRunner as AsyncioSearchRunner

logger = logging.getLogger(__name__)


@dataclass
class Container:
    engine: AsyncEngine
    uow: UnitOfWork
    runner: AsyncioSearchRunner
    mediator: Mediator
    channels: list[grpc.aio.Channel] = field(default_factory=list)

    async def close(self) -> None:
        await self.runner.cancel_all()
        for channel in self.channels:
            await channel.close()
        await self.engine.dispose()


def build_collector(settings: Settings, channels: list[grpc.aio.Channel]) -> CollectorClient:
    if settings.collector_mode == "stub":
        logger.warning("COLLECTOR_MODE=stub — посты-фикстуры без collector_service, НЕ для демо")
        fail = tuple(p for p in settings.stub_fail_platforms.split(",") if p)
        return StubCollectorClient(fail_platforms=fail)
    # канал к соседу; соединение установится при первом вызове
    channel = grpc.aio.insecure_channel(settings.collector_grpc_target)
    channels.append(channel)
    return GrpcCollectorClient(
        channel,
        resolve_timeout=settings.collector_resolve_timeout,
        collect_timeout=settings.collector_collect_timeout,
    )


def build_ml(settings: Settings, channels: list[grpc.aio.Channel]) -> MlClient:
    if settings.ml_mode == "stub":
        logger.warning("ML_MODE=stub — оценки-заглушки без ml_service, НЕ для демо")
        return StubMl()
    channel = grpc.aio.insecure_channel(settings.ml_grpc_target)
    channels.append(channel)
    return GrpcMlClient(
        channel,
        analyze_timeout=settings.ml_analyze_timeout,
        score_timeout=settings.ml_score_timeout,
        group_timeout=settings.ml_group_timeout,
    )


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings)
    uow = SqlAlchemyUnitOfWork(create_session_factory(engine))

    channels: list[grpc.aio.Channel] = []
    collector = build_collector(settings, channels)
    ml = build_ml(settings, channels)

    pipeline = Pipeline(
        uow,
        collector,
        ml,
        asyncio.Semaphore(settings.collect_concurrency),
        settings.target_timeout,
    )
    runner = AsyncioSearchRunner(pipeline)
    return Container(
        engine=engine,
        uow=uow,
        runner=runner,
        mediator=build_mediator(uow, collector, runner),
        channels=channels,
    )


def build_mediator(uow: UnitOfWork, collector: CollectorClient, runner: SearchRunner) -> Mediator:
    """Единственное место, где сценарии привязываются к командам."""
    m = Mediator()
    # источники
    m.register(ResolveSourceQuery, ResolveSourceQueryHandler(uow, collector))
    m.register(CreateSourceCommand, CreateSourceCommandHandler(uow, collector))
    m.register(ListSourcesQuery, ListSourcesQueryHandler(uow, collector))
    m.register(UpdateSourceCommand, UpdateSourceCommandHandler(uow, collector))
    m.register(DeleteSourceCommand, DeleteSourceCommandHandler(uow, collector))
    m.register(ImportSourcesCommand, ImportSourcesCommandHandler(uow, collector))
    # поиск
    m.register(StartSearchCommand, StartSearchCommandHandler(uow, runner))
    m.register(GetSearchQuery, GetSearchQueryHandler(uow))
    m.register(ListSearchesQuery, ListSearchesQueryHandler(uow, runner))
    m.register(RetrySearchCommand, RetrySearchCommandHandler(uow, runner))
    m.register(CancelSearchCommand, CancelSearchCommandHandler(uow, runner))
    # подборка
    m.register(ListResultsQuery, ListResultsQueryHandler(uow))
    m.register(ListGroupsQuery, ListGroupsQueryHandler(uow))
    m.register(SetExcludedCommand, SetExcludedCommandHandler(uow, runner))
    m.register(ExportSearchQuery, ExportSearchQueryHandler(uow))
    return m


async def mark_interrupted_searches(uow: UnitOfWork) -> int:
    """Все RUNNING/QUEUED на старте → FAILED с warning: их фоновые задачи умерли с процессом."""
    async with uow:
        orphans = await uow.searches.list_running_or_queued()
        for search in orphans:
            targets = await uow.targets.list_by_search(search.id)
            for t in targets:
                if not t.is_finished:
                    t.mark_failed("INTERRUPTED", "Поиск прерван перезапуском сервиса")
                    await uow.targets.save(t)
            search.status = SearchStatus.FAILED
            search.stage = SearchStage.DONE
            search.add_warning("Поиск прерван перезапуском сервиса")
            search.finished_at = utcnow()
            await uow.searches.save(search)
        await uow.commit()
    if orphans:
        logger.warning("Прерванные поиски помечены FAILED: %d", len(orphans))
    return len(orphans)

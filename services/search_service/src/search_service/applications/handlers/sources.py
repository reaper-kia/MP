"""Каталог источников. Задача B2-02 (импорт — B2-10)."""

from dataclasses import dataclass

from search_service.applications.commands.sources import (
    CreateSourceCommand,
    DeleteSourceCommand,
    ImportSourcesCommand,
    UpdateSourceCommand,
)
from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.collector import CollectorClient
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.queries.sources import ListSourcesQuery, ResolveSourceQuery
from search_service.applications.results.read_models import (
    ImportReport,
    SourcePage,
    SourcePreviewView,
    SourceView,
)


@dataclass
class ResolveSourceQueryHandler:
    uow_factory: UnitOfWorkFactory
    collector: CollectorClient

    async def handle(self, query: ResolveSourceQuery) -> SourcePreviewView:
        """1) collector.resolve_source(url) — ошибки соседа пробрасываются как есть (UpstreamError);
        2) is_closed → SOURCE_PRIVATE; 3) поиск в каталоге по (platform, external_id) →
        existing_source_id."""
        raise NotImplementedYetError("ResolveSource: B2-02")


@dataclass
class CreateSourceCommandHandler:
    uow_factory: UnitOfWorkFactory
    collector: CollectorClient

    async def handle(self, cmd: CreateSourceCommand) -> SourceView:
        """resolve (вне транзакции) → дубль? SourceAlreadyExistsError → Source.create → commit."""
        raise NotImplementedYetError("CreateSource: B2-02")


@dataclass
class ListSourcesQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListSourcesQuery) -> SourcePage:
        """Фильтры platforms / q (ILIKE по name и url) / is_active; limit 1..200; total.

        Удалённые (deleted_at) не показываем."""
        raise NotImplementedYetError("ListSources: B2-02")


@dataclass
class UpdateSourceCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: UpdateSourceCommand) -> SourceView:
        """Меняем только поля, которые не None. Нет источника → SourceNotFoundError."""
        raise NotImplementedYetError("UpdateSource: B2-02")


@dataclass
class DeleteSourceCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: DeleteSourceCommand) -> None:
        """Мягкое удаление (deleted_at): история поисков хранит снимок имени и ссылки."""
        raise NotImplementedYetError("DeleteSource: B2-02")


@dataclass
class ImportSourcesCommandHandler:
    uow_factory: UnitOfWorkFactory
    collector: CollectorClient

    async def handle(self, cmd: ImportSourcesCommand) -> ImportReport:
        """openpyxl: A — ссылка, B — название, C — региональный (да/нет); по строке — как Create."""
        raise NotImplementedYetError("ImportSources: B2-10")

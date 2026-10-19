from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog

from search_service.applications.commands.sources import (
    CreateSourceCommand,
    DeleteSourceCommand,
    ImportSourcesCommand,
    UpdateSourceCommand,
)
from search_service.applications.exceptions import UpstreamError
from search_service.applications.handlers.errors import SOURCE_PRIVATE_MESSAGE, domain_errors
from search_service.applications.handlers.source_import import parse_sources_xlsx
from search_service.applications.handlers.views import preview_view, source_view
from search_service.applications.ports.collector_client import CollectorClient, SourceInfo
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.sources import ListSourcesQuery, ResolveSourceQuery
from search_service.applications.results.read_models import (
    ErrorInfoView,
    ImportReport,
    ImportRowErrorView,
    SourcePage,
    SourcePreviewView,
    SourceView,
)
from search_service.domain.entities import Source
from search_service.domain.errors import (
    CollectorError,
    DomainError,
    NotFoundError,
    SourceAlreadyExists,
)

log = structlog.get_logger()


@dataclass
class ResolveRequest:
    url: str


@dataclass
class CreateRequest:
    url: str
    name: str | None = None
    is_regional: bool = True
    notes: str = ""


@dataclass
class ListRequest:
    platforms: list[str] | None = None
    q: str | None = None
    is_active: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class UpdateRequest:
    source_id: uuid.UUID
    name: str | None = None
    is_regional: bool | None = None
    is_active: bool | None = None
    notes: str | None = None


@dataclass
class DeleteRequest:
    source_id: uuid.UUID


class SourceHandler:
    def __init__(self, uow: UnitOfWork, collector: CollectorClient) -> None:
        self.uow = uow
        self.collector = collector

    async def resolve(self, req: ResolveRequest) -> tuple[SourceInfo, Source | None]:
        info = await self.collector.resolve_source(req.url)
        async with self.uow:
            existing = await self.uow.sources.get_by_key(info.platform, info.external_id)
            return info, existing

    async def create(self, req: CreateRequest) -> Source:
        info = await self.collector.resolve_source(req.url)
        if info.is_closed:
            raise DomainError("SOURCE_PRIVATE")
        name = req.name or info.name or info.screen_name
        async with self.uow:
            existing = await self.uow.sources.get_by_key(info.platform, info.external_id)
            if existing and existing.is_alive:
                raise SourceAlreadyExists(f"{info.platform}:{info.external_id}")
            source = Source(
                platform=info.platform,
                external_id=info.external_id,
                screen_name=info.screen_name,
                url=info.url,
                name=name,
                city=info.city,
                is_regional=req.is_regional,
                notes=req.notes,
            )
            await self.uow.sources.add(source)
            await self.uow.commit()
            return source

    async def list(self, req: ListRequest) -> tuple[list[Source], int, bool]:
        limit = max(1, min(req.limit or 50, 200))
        async with self.uow:
            sources, total = await self.uow.sources.list(
                platforms=req.platforms,
                q=req.q,
                is_active=req.is_active,
                limit=limit,
                offset=req.offset,
            )
            return sources, total, req.offset + len(sources) < total

    async def update(self, req: UpdateRequest) -> Source:
        async with self.uow:
            source = await self.uow.sources.get_by_id(req.source_id)
            if not source or not source.is_alive:
                raise NotFoundError("SOURCE_NOT_FOUND")
            updates = {k: v for k, v in req.__dict__.items() if k != "source_id" and v is not None}
            source.update(**updates)
            await self.uow.sources.save(source)
            await self.uow.commit()
            return source

    async def delete(self, req: DeleteRequest) -> None:
        async with self.uow:
            source = await self.uow.sources.get_by_id(req.source_id)
            if not source or not source.is_alive:
                raise NotFoundError("SOURCE_NOT_FOUND")
            source.soft_delete()
            await self.uow.sources.save(source)
            await self.uow.commit()


# ---------------------------------------------------------------------------
# Хэндлеры медиатора для gRPC-транспорта (регистрируются в dependencies.build_mediator):
# команда → SourceHandler выше → read model.
# ---------------------------------------------------------------------------


@dataclass
class ResolveSourceQueryHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, query: ResolveSourceQuery) -> SourcePreviewView:
        """1) collector.resolve_source(url) — ошибки соседа пробрасываются как есть (UpstreamError);
        2) is_closed → SOURCE_PRIVATE; 3) поиск в каталоге по (platform, external_id) →
        existing_source_id."""
        with domain_errors():
            info, existing = await SourceHandler(self.uow, self.collector).resolve(
                ResolveRequest(url=query.url)
            )
        if info.is_closed:
            raise UpstreamError("collector", "SOURCE_PRIVATE", SOURCE_PRIVATE_MESSAGE)
        return preview_view(info, existing)


@dataclass
class CreateSourceCommandHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, cmd: CreateSourceCommand) -> SourceView:
        """resolve (вне транзакции) → дубль? SourceAlreadyExistsError → Source → commit."""
        with domain_errors():
            source = await SourceHandler(self.uow, self.collector).create(
                CreateRequest(
                    url=cmd.url, name=cmd.name, is_regional=cmd.is_regional, notes=cmd.notes
                )
            )
        return source_view(source)


@dataclass
class ListSourcesQueryHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, query: ListSourcesQuery) -> SourcePage:
        """Фильтры platforms / q (ILIKE по name и url) / is_active; limit 1..200; total.

        Удалённые (deleted_at) не показываем."""
        sources, total, has_more = await SourceHandler(self.uow, self.collector).list(
            ListRequest(
                platforms=[p.value for p in query.platforms] or None,
                q=query.q or None,
                is_active=query.is_active,
                limit=query.limit,
                offset=query.offset,
            )
        )
        return SourcePage(items=[source_view(s) for s in sources], total=total, has_more=has_more)


@dataclass
class UpdateSourceCommandHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, cmd: UpdateSourceCommand) -> SourceView:
        """Меняем только поля, которые не None. Нет источника → SourceNotFoundError."""
        with domain_errors():
            source = await SourceHandler(self.uow, self.collector).update(
                UpdateRequest(
                    source_id=cmd.source_id,
                    name=cmd.name,
                    is_regional=cmd.is_regional,
                    is_active=cmd.is_active,
                    notes=cmd.notes,
                )
            )
        return source_view(source)


@dataclass
class DeleteSourceCommandHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, cmd: DeleteSourceCommand) -> None:
        """Мягкое удаление (deleted_at): история поисков хранит снимок имени и ссылки."""
        with domain_errors():
            await SourceHandler(self.uow, self.collector).delete(
                DeleteRequest(source_id=cmd.source_id)
            )


def row_error(error: Exception) -> ErrorInfoView:
    """Почему строка не создалась: публичный код и русский текст, как у одиночного CreateSource."""
    if isinstance(error, UpstreamError):
        return ErrorInfoView(error.code, error.message)
    if isinstance(error, CollectorError):
        return ErrorInfoView(error.code, str(error))
    if isinstance(error, DomainError) and str(error) == "SOURCE_PRIVATE":
        return ErrorInfoView("SOURCE_PRIVATE", SOURCE_PRIVATE_MESSAGE)
    return ErrorInfoView("INTERNAL", "Не удалось обработать строку")


@dataclass
class ImportSourcesCommandHandler:
    uow: UnitOfWork
    collector: CollectorClient

    async def handle(self, cmd: ImportSourcesCommand) -> ImportReport:
        """openpyxl: A — ссылка, B — название, C — региональный (да/нет); по строке — как Create.

        Строки идут по очереди (не параллельно): дубли внутри одного файла честно находятся
        как «уже есть», а площадки не получают пачку запросов разом."""
        with domain_errors():
            rows, bad = parse_sources_xlsx(cmd.xlsx)
        handler = SourceHandler(self.uow, self.collector)
        created = duplicates = 0
        failed = [
            ImportRowErrorView(b.row, b.value, ErrorInfoView("VALIDATION_ERROR", b.message))
            for b in bad
        ]
        for row in rows:
            try:
                await handler.create(
                    CreateRequest(url=row.url, name=row.name, is_regional=row.is_regional)
                )
                created += 1
            except SourceAlreadyExists:
                duplicates += 1
            except Exception as e:
                if not isinstance(e, DomainError | UpstreamError):
                    log.exception("import row failed", row=row.row)
                failed.append(ImportRowErrorView(row.row, row.url, row_error(e)))
        failed.sort(key=lambda f: f.row)
        return ImportReport(created=created, duplicates=duplicates, failed=failed)

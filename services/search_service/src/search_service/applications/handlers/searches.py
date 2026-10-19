from __future__ import annotations

import uuid
from dataclasses import dataclass

from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.collector import CollectorClient
from search_service.applications.ports.ml import MlClient
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.results.read_models import SearchPage, SearchView
from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import SearchMode, TargetKind
from search_service.domain.errors import NotFoundError, SearchInvalidParams
from search_service.domain.value_objects import Period


@dataclass
class StartSearchRequest:
    query: str
    period_from: str
    period_to: str
    mode: SearchMode
    platforms: list[str]
    source_ids: list[uuid.UUID]


class SearchHandler:
    def __init__(self, uow: UnitOfWork, runner):
        self.uow = uow
        self.runner = runner

    async def start(self, req: StartSearchRequest) -> Search:
        # валидация
        if not req.query or len(req.query.strip()) < 3:
            raise SearchInvalidParams("query", "слишком короткий (минимум 3 символа)")

        from datetime import date

        try:
            pf = date.fromisoformat(req.period_from)
            pt = date.fromisoformat(req.period_to)
        except ValueError as e:
            raise SearchInvalidParams("period", f"неверный формат даты: {e}")

        period = Period(from_date=pf, to_date=pt)

        if req.mode is SearchMode.SELECTED and not req.source_ids:
            raise SearchInvalidParams("source_ids", "в режиме selected нужны источники")

        async with self.uow:
            # снимок источников
            targets: list[SearchTarget] = []
            if req.mode is SearchMode.SELECTED:
                sources = await self.uow.sources.get_by_ids(req.source_ids)
                by_id = {s.id: s for s in sources}
                for sid in req.source_ids:
                    src = by_id.get(sid)
                    if not src or not src.is_alive:
                        raise NotFoundError(f"SOURCE_NOT_FOUND: {sid}")
                    if src.platform not in req.platforms:
                        raise SearchInvalidParams(
                            "source_ids",
                            f"источник {src.name} на площадке {src.platform} не входит в выбранные {req.platforms}",
                        )
                    targets.append(
                        SearchTarget(
                            kind=TargetKind.SOURCE,
                            platform=src.platform,
                            name=src.name,
                            url=src.url,
                            source_id=src.id,
                        )
                    )
            else:
                for p in req.platforms:
                    targets.append(
                        SearchTarget(
                            kind=TargetKind.PLATFORM_SEARCH,
                            platform=p,
                            name=p.upper(),
                        )
                    )

            search = Search(
                query=req.query,
                period=period,
                mode=req.mode,
                platforms=req.platforms,
                source_ids=req.source_ids,
                targets=targets,
            )
            await self.uow.searches.add(search)
            for t in targets:
                t.search_id = search.id
                await self.uow.targets.add(t)
            await self.uow.commit()

        # фоновый запуск
        await self.runner.launch(search.id)
        return search

    async def get(self, search_id: uuid.UUID) -> Search:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            return search

    async def list(self, limit: int = 50, offset: int = 0):
        limit = max(1, min(limit or 50, 200))
        async with self.uow:
            return await self.uow.searches.list(limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Хэндлеры медиатора для gRPC-транспорта (каркас из main, регистрируются в
# dependencies.build_mediator). Пока не связаны с реализацией выше.
# ---------------------------------------------------------------------------


@dataclass
class StartSearchCommandHandler:
    uow_factory: UnitOfWorkFactory
    collector: CollectorClient
    ml: MlClient

    async def handle(self, cmd: StartSearchCommand) -> SearchView:
        """1) валидация → SearchInvalidParamsError("<поле>: <текст>"); период —
        UtcPeriod.from_local_dates; 2) Search + цели (снимок name/url) в одной транзакции;
        3) запустить пайплайн фоновой задачей (B2-04) и сразу вернуть status=QUEUED."""
        raise NotImplementedYetError("StartSearch: B2-03")


@dataclass
class GetSearchQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: GetSearchQuery) -> SearchView:
        """Поиск + цели + счётчики (одним SQL по search_results) + прогресс."""
        raise NotImplementedYetError("GetSearch: B2-03")


@dataclass
class ListSearchesQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListSearchesQuery) -> SearchPage:
        """Новые сверху, без targets; limit+1 для has_more (как в шаблоне)."""
        raise NotImplementedYetError("ListSearches: B2-03")


@dataclass
class RetrySearchCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: RetrySearchCommand) -> SearchView:
        """Только FAILED цели (или указанные); поиск ещё идёт → SearchNotFinishedError."""
        raise NotImplementedYetError("RetrySearch: B2-09")


@dataclass
class CancelSearchCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: CancelSearchCommand) -> SearchView:
        """Отменить фоновую задачу; незавершённые цели → SKIPPED; статус CANCELLED."""
        raise NotImplementedYetError("CancelSearch: B2-09")

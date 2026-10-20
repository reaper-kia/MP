from __future__ import annotations

import uuid
from dataclasses import dataclass

from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.handlers.control import ControlHandler
from search_service.applications.handlers.errors import domain_errors
from search_service.applications.handlers.views import counts_view, search_view
from search_service.applications.ports.runner import SearchRunner
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.results.read_models import SearchPage, SearchView
from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import SearchMode, TargetKind
from search_service.domain.errors import NotFoundError, SearchInvalidParams
from search_service.domain.value_objects import Period

GLOBAL_CATALOG_LIMIT = 200  # сколько источников каталога подключаем к «везде»


@dataclass
class StartSearchRequest:
    query: str
    period_from: str
    period_to: str
    mode: SearchMode
    platforms: list[str]
    source_ids: list[uuid.UUID]


class SearchHandler:
    def __init__(self, uow: UnitOfWork, runner: SearchRunner) -> None:
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
            raise SearchInvalidParams("period", f"неверный формат даты: {e}") from e

        period = Period(from_date=pf, to_date=pt)

        if req.mode is SearchMode.SELECTED and not req.source_ids:
            raise SearchInvalidParams("source_ids", "в режиме selected нужны источники")
        if req.mode is SearchMode.GLOBAL and not req.platforms:
            raise SearchInvalidParams("platforms", "выберите хотя бы одну площадку")

        platforms = list(dict.fromkeys(req.platforms))
        async with self.uow:
            # снимок источников
            targets: list[SearchTarget] = []
            if req.mode is SearchMode.SELECTED:
                # по контракту в SELECTED площадки берутся из источников, platforms игнорируется
                platforms = []
                sources = await self.uow.sources.get_by_ids(req.source_ids)
                by_id = {s.id: s for s in sources}
                for sid in dict.fromkeys(req.source_ids):
                    src = by_id.get(sid)
                    if not src or not src.is_alive:
                        raise NotFoundError(f"SOURCE_NOT_FOUND: {sid}")
                    if src.platform not in platforms:
                        platforms.append(src.platform)
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
                for p in platforms:
                    targets.append(
                        SearchTarget(
                            kind=TargetKind.PLATFORM_SEARCH,
                            platform=p,
                            name=p.upper(),
                        )
                    )
                # «везде» = поиск по площадке + стены всех активных региональных источников
                # каталога на этих площадках: поиск площадки (VK — Яндекс site:vk.com) неполный
                # и может быть недоступен, а свои проверенные паблики читаются всегда
                catalog, _ = await self.uow.sources.list(
                    platforms=platforms, is_active=True, limit=GLOBAL_CATALOG_LIMIT
                )
                for src in catalog:
                    if src.is_alive and src.is_regional and src.platform in platforms:
                        targets.append(
                            SearchTarget(
                                kind=TargetKind.SOURCE,
                                platform=src.platform,
                                name=src.name,
                                url=src.url,
                                source_id=src.id,
                            )
                        )

            search = Search(
                query=req.query,
                period=period,
                mode=req.mode,
                platforms=platforms,
                source_ids=list(dict.fromkeys(req.source_ids)),
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

    async def list(self, limit: int = 50, offset: int = 0) -> tuple[list[Search], int, bool]:
        limit = max(1, min(limit or 50, 200))
        async with self.uow:
            return await self.uow.searches.list(limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Хэндлеры медиатора для gRPC-транспорта (регистрируются в dependencies.build_mediator):
# команда → SearchHandler / ControlHandler → read model.
# ---------------------------------------------------------------------------


async def load_search_view(uow: UnitOfWork, search_id: uuid.UUID) -> SearchView:
    """Поиск + цели + счётчики (одним SQL по search_results) + прогресс."""
    async with uow:
        search = await uow.searches.get_with_targets(search_id)
        if search is None:
            raise NotFoundError("SEARCH_NOT_FOUND")
        counts = await uow.results.counts(search_id)
    return search_view(search, counts_view(counts))


@dataclass
class StartSearchCommandHandler:
    uow: UnitOfWork
    runner: SearchRunner

    async def handle(self, cmd: StartSearchCommand) -> SearchView:
        """1) валидация → SearchInvalidParamsError("<поле>: <текст>"); период — по Красноярску;
        2) Search + цели (снимок name/url) в одной транзакции;
        3) пайплайн запускается фоновой задачей (B2-04), сразу возвращаем status=QUEUED."""
        with domain_errors():
            search = await SearchHandler(self.uow, self.runner).start(
                StartSearchRequest(
                    query=cmd.query,
                    period_from=cmd.period_from.isoformat(),
                    period_to=cmd.period_to.isoformat(),
                    mode=cmd.mode,
                    platforms=[p.value for p in cmd.platforms],
                    source_ids=list(cmd.source_ids),
                )
            )
            return await load_search_view(self.uow, search.id)


@dataclass
class GetSearchQueryHandler:
    uow: UnitOfWork

    async def handle(self, query: GetSearchQuery) -> SearchView:
        """Поиск + цели + счётчики + прогресс."""
        with domain_errors():
            return await load_search_view(self.uow, query.search_id)


@dataclass
class ListSearchesQueryHandler:
    uow: UnitOfWork
    runner: SearchRunner

    async def handle(self, query: ListSearchesQuery) -> SearchPage:
        """Новые сверху, без targets."""
        searches, _, has_more = await SearchHandler(self.uow, self.runner).list(
            limit=query.limit, offset=query.offset
        )
        async with self.uow:
            items = [
                search_view(s, counts_view(await self.uow.results.counts(s.id)), with_targets=False)
                for s in searches
            ]
        return SearchPage(items=items, has_more=has_more)


@dataclass
class RetrySearchCommandHandler:
    uow: UnitOfWork
    runner: SearchRunner

    async def handle(self, cmd: RetrySearchCommand) -> SearchView:
        """Только FAILED цели (или указанные); поиск ещё идёт → SearchNotFinishedError."""
        with domain_errors():
            search = await ControlHandler(self.uow, self.runner).retry(
                cmd.search_id, list(cmd.target_ids) or None
            )
            return await load_search_view(self.uow, search.id)


@dataclass
class CancelSearchCommandHandler:
    uow: UnitOfWork
    runner: SearchRunner

    async def handle(self, cmd: CancelSearchCommand) -> SearchView:
        """Отменить фоновую задачу; незавершённые цели → SKIPPED; статус CANCELLED."""
        with domain_errors():
            search = await ControlHandler(self.uow, self.runner).cancel(cmd.search_id)
            return await load_search_view(self.uow, search.id)

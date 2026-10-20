from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog

from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.exceptions import UpstreamError
from search_service.applications.handlers.control import ControlHandler
from search_service.applications.handlers.errors import domain_errors
from search_service.applications.handlers.pipeline import WAITING_FOR_TWIN
from search_service.applications.handlers.views import counts_view, search_view
from search_service.applications.ports.collector_client import CollectorClient
from search_service.applications.ports.runner import SearchRunner
from search_service.applications.ports.search_cache import SearchCache
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.results.read_models import SearchPage, SearchView
from search_service.applications.search_cache import search_cache_key
from search_service.domain.entities import Search, SearchTarget, utcnow
from search_service.domain.enums import SearchMode, SearchStatus, TargetKind
from search_service.domain.errors import NotFoundError, SearchInvalidParams
from search_service.domain.value_objects import Period

GLOBAL_CATALOG_LIMIT = 200  # сколько источников каталога подключаем к «везде»
NO_GLOBAL_TARGETS = (
    "на выбранных площадках нет активных источников в каталоге, а поиска по всей площадке нет — "
    "добавьте источники на странице «Источники»"
)

log = structlog.get_logger()


@dataclass
class StartSearchRequest:
    query: str
    period_from: str
    period_to: str
    mode: SearchMode
    platforms: list[str]
    source_ids: list[uuid.UUID]
    fresh: bool = False  # мимо кэша готовых подборок
    owner: str = ""  # анонимный id браузера: история у каждого своя


class SearchHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        runner: SearchRunner,
        collector: CollectorClient | None = None,
        cache: SearchCache | None = None,
    ) -> None:
        self.uow = uow
        self.runner = runner
        self.collector = collector
        self.cache = cache

    async def _from_cache(self, key: str, owner: str) -> Search | None:
        """Готовая подборка с теми же параметрами (B2-20) → её копия: новый поиск сразу в
        финальном статусе. Копия, а не тот же search_id: исключения одного пользователя не должны
        появляться у другого. Исходного поиска уже нет (или он перезапущен) — промах."""
        if self.cache is None:
            return None
        source_id = await self.cache.get(key)
        if source_id is None:
            log.info("cache miss", key=key)
            return None
        new_id = uuid.uuid4()
        search: Search | None = None
        async with self.uow:
            if await self.uow.searches.clone_finished(source_id, new_id, utcnow(), owner):
                await self.uow.commit()
                search = await self.uow.searches.get_with_targets(new_id)
        if search is None:
            log.info("cache miss", key=key, reason="source search gone or not finished")
            return None
        log.info("cache hit", key=key, from_search_id=str(source_id), search_id=str(new_id))
        return search

    async def _running_twin(self, key: str) -> uuid.UUID | None:
        """Такой же поиск сейчас идёт (в очереди или собирает) → его id: повтор подождёт его,
        а не запустит второй сбор с моделью (B2-20 P2). Отметка устарела — None."""
        if self.cache is None:
            return None
        leader_id = await self.cache.get_running(key)
        if leader_id is None:
            return None
        async with self.uow:
            leader = await self.uow.searches.get_by_id(leader_id)
        if leader is None or SearchStatus(leader.status).is_final:
            return None
        log.info("cache join planned", key=key, leader_id=str(leader_id))
        return leader_id

    async def _global_platforms(self, platforms: list[str]) -> set[str]:
        """Где «везде» добавляет поиск по всей площадке: только там, где collector его умеет.

        Без collector (старые тесты) — на всех выбранных. collector не ответил — ни на одной:
        «везде» всё равно читает все источники каталога, а заведомо падающих целей не создаём.
        """
        if self.collector is None:
            return set(platforms)
        try:
            return await self.collector.global_platforms()
        except UpstreamError as e:
            log.warning("global platforms unknown — only catalog sources", error=str(e))
            return set()

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
        use_cache = self.cache is not None and self.cache.enabled
        key = search_cache_key(
            query=req.query,
            period_from=pf,
            period_to=pt,
            mode=req.mode,
            platforms=platforms,
            source_ids=req.source_ids,
        )
        leader_id: uuid.UUID | None = None
        if use_cache and not req.fresh:
            cached = await self._from_cache(key, req.owner)
            if cached is not None:
                return cached
            leader_id = await self._running_twin(key)

        searchable: set[str] = set()
        if req.mode is SearchMode.GLOBAL:
            searchable = await self._global_platforms(platforms)
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
                # «везде» = все активные источники каталога на выбранных площадках + поиск по
                # всей площадке там, где collector его умеет (новостные сайты — RSS; VK / OK —
                # только с ключом Yandex Search API). Привязку к краю у нерегиональных источников
                # проверяет оценка по тексту (scoring.py), поэтому их тоже читаем
                for p in platforms:
                    if p in searchable:
                        targets.append(
                            SearchTarget(
                                kind=TargetKind.PLATFORM_SEARCH,
                                platform=p,
                                name=p.upper(),
                            )
                        )
                catalog, _ = await self.uow.sources.list(
                    platforms=platforms, is_active=True, limit=GLOBAL_CATALOG_LIMIT
                )
                for src in catalog:
                    if src.is_alive and src.platform in platforms:
                        targets.append(
                            SearchTarget(
                                kind=TargetKind.SOURCE,
                                platform=src.platform,
                                name=src.name,
                                url=src.url,
                                source_id=src.id,
                            )
                        )
                if not targets:
                    raise SearchInvalidParams("platforms", NO_GLOBAL_TARGETS)

            search = Search(
                query=req.query,
                period=period,
                mode=req.mode,
                platforms=platforms,
                source_ids=list(dict.fromkeys(req.source_ids)),
                targets=targets,
                owner=req.owner,
            )
            if leader_id is not None:
                search.add_warning(WAITING_FOR_TWIN)
            await self.uow.searches.add(search)
            for t in targets:
                t.search_id = search.id
                await self.uow.targets.add(t)
            await self.uow.commit()

        # фоновый запуск: повтор ждёт оригинал, иначе — свой пайплайн, и повторы будут ждать его
        if leader_id is not None:
            await self.runner.follow(search.id, leader_id)
        else:
            if use_cache and self.cache is not None:
                await self.cache.put_running(key, search.id)
            await self.runner.launch(search.id)
        return search

    async def get(self, search_id: uuid.UUID) -> Search:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            return search

    async def list(
        self, limit: int = 50, offset: int = 0, *, owner: str
    ) -> tuple[list[Search], int, bool]:
        """История одного браузера: чужие поиски не видны (owner пустой — история пустая)."""
        limit = max(1, min(limit or 50, 200))
        async with self.uow:
            return await self.uow.searches.list(owner=owner, limit=limit, offset=offset)


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
    collector: CollectorClient | None = None
    cache: SearchCache | None = None

    async def handle(self, cmd: StartSearchCommand) -> SearchView:
        """1) валидация → SearchInvalidParamsError("<поле>: <текст>"); период — по Красноярску;
        2) тот же поиск недавно уже был и fresh=false → копия готовой подборки (B2-20);
        3) иначе Search + цели (снимок name/url) в одной транзакции;
        4) пайплайн запускается фоновой задачей (B2-04), сразу возвращаем status=QUEUED."""
        with domain_errors():
            handler = SearchHandler(self.uow, self.runner, self.collector, self.cache)
            search = await handler.start(
                StartSearchRequest(
                    query=cmd.query,
                    period_from=cmd.period_from.isoformat(),
                    period_to=cmd.period_to.isoformat(),
                    mode=cmd.mode,
                    platforms=[p.value for p in cmd.platforms],
                    source_ids=list(cmd.source_ids),
                    fresh=cmd.fresh,
                    owner=cmd.ctx.actor,
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
            limit=query.limit, offset=query.offset, owner=query.ctx.actor
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

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import structlog

from search_service.applications.handlers.save import SaveHandler
from search_service.applications.handlers.scoring import ScoringHandler, analysis_to_dict
from search_service.applications.ports.collector_client import CollectorClient, RawPost
from search_service.applications.ports.ml_client import MlClient, QueryAnalysis
from search_service.applications.ports.search_cache import SearchCache
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.search_cache import key_of
from search_service.domain.entities import Search, SearchTarget, utcnow
from search_service.domain.enums import Platform, QueryType, SearchStage, SearchStatus
from search_service.domain.errors import CollectorError, NotFoundError

log = structlog.get_logger()

CACHEABLE_STATUSES = frozenset({SearchStatus.COMPLETED, SearchStatus.PARTIAL})
# пока повтор ждёт такой же идущий поиск (B2-20 P2); копия заменит его предупреждениями оригинала
WAITING_FOR_TWIN = "Такой же поиск уже идёт — покажем его подборку, как только он закончится"

# русские сообщения об ошибках по коду
ERROR_MESSAGES = {
    "PLATFORM_UNAVAILABLE": "{platform} недоступна",
    "TIMEOUT": "{platform} не ответила за 60 секунд",
    "SOURCE_NOT_FOUND": "Источник не найден на площадке",
    "SOURCE_PRIVATE": "Группа закрыта",
    "RATE_LIMITED": "Превышен лимит запросов к площадке",
}


@contextmanager
def timed_stage(search_id: uuid.UUID, stage: str, **fields: str) -> Iterator[None]:
    """Длительность стадии в лог (B2-11): по этим строкам считаем среднее время поиска.

    Цели собираются и сразу оцениваются (конвейер), поэтому стадия collecting включает оценку, а
    «чистое» время сбора и оценки по цели — строки target_collect / target_scoring."""
    started = time.perf_counter()
    try:
        yield
    finally:
        log.info(
            "search stage finished",
            search_id=str(search_id),
            stage=stage,
            seconds=round(time.perf_counter() - started, 2),
            **fields,
        )


@dataclass
class TargetJob:
    target: SearchTarget
    posts: list[RawPost]


def _platform_title(platform: str) -> str:
    try:
        return Platform(platform).display
    except ValueError:
        return platform


def _require(search: Search | None, search_id: uuid.UUID) -> Search:
    if search is None:
        raise NotFoundError(f"SEARCH_NOT_FOUND: {search_id}")
    return search


class Pipeline:
    """Основной пайплайн поиска: analyzing → collecting → scoring → grouping."""

    def __init__(
        self,
        uow: UnitOfWork,
        collector: CollectorClient,
        ml: MlClient,
        semaphore: asyncio.Semaphore,
        target_timeout: int = 60,
        *,
        show_degraded_warning: bool = True,
        cache: SearchCache | None = None,
    ) -> None:
        self.uow = uow
        self.cache = cache
        self.collector = collector
        self.ml = ml
        self.sem = semaphore
        self.target_timeout = target_timeout
        self.show_degraded_warning = show_degraded_warning
        self.save = SaveHandler(uow)
        self.scorer = ScoringHandler(uow, ml)

    async def run(self, search_id: uuid.UUID) -> None:
        try:
            with timed_stage(search_id, "total"):
                await self._run_inner(search_id)
        except Exception as e:
            log.exception("pipeline crashed", search_id=str(search_id), error=str(e))
            await self._force_fail(search_id, f"Непредвиденная ошибка: {e}")
        finally:
            await self._drop_running(search_id)

    async def _drop_running(self, search_id: uuid.UUID) -> None:
        """Поиск закончился (как угодно) — повторы больше не ждут его, а берут кэш или ищут сами."""
        if self.cache is None or not self.cache.enabled:
            return
        try:
            async with self.uow:
                search = await self.uow.searches.get_by_id(search_id)
            if search is not None:
                await self.cache.drop_running(key_of(search), search_id)
        except Exception as e:  # noqa: BLE001 — отметка сама истечёт по TTL
            log.warning("running mark not dropped", search_id=str(search_id), error=str(e))

    async def is_final(self, search_id: uuid.UUID) -> bool:
        """Поиск закончился или пропал (для повтора, который ждёт оригинал из другого процесса)."""
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
        return search is None or SearchStatus(search.status).is_final

    async def adopt(self, search_id: uuid.UUID, leader_id: uuid.UUID) -> bool:
        """Повтор search_id получает копию готовой подборки leader_id под своим id (B2-20 P2).
        Оригинал не дал подборки или повтор отменён → False, ничего не меняется."""
        async with self.uow:
            if not await self.uow.searches.replace_with_copy(leader_id, search_id, utcnow()):
                return False
            await self.uow.commit()
        log.info("cache join", search_id=str(search_id), from_search_id=str(leader_id))
        return True

    async def forget_twin(self, search_id: uuid.UUID) -> None:
        """Оригинал упал или отменён — повтор ищет сам: убираем «такой же поиск уже идёт»."""
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
            if search is None or WAITING_FOR_TWIN not in search.warnings:
                return
            search.warnings = [w for w in search.warnings if w != WAITING_FOR_TWIN]
            await self.uow.searches.save(search)
            await self.uow.commit()

    async def _run_inner(self, search_id: uuid.UUID) -> None:
        # 1. старт
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.start()
            if getattr(self.collector, "is_stub", False):
                search.add_warning(
                    "Коллектор в режиме имитации (COLLECTOR_MODE=stub) — посты тестовые"
                )
            if getattr(self.ml, "is_stub", False):
                search.add_warning("ML в режиме имитации (ML_MODE=stub)")
            await self.uow.searches.save(search)
            await self.uow.commit()

        # 2. analyze query
        with timed_stage(search_id, SearchStage.ANALYZING_QUERY.value):
            analysis, ml_warning = await self._analyze(search)
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            search.query_type = analysis.query_type
            # разбор храним целиком: он нужен ScorePosts (ScoringHandler.score_results)
            search.query_analysis = analysis_to_dict(analysis)
            if ml_warning:
                search.add_warning(ml_warning)
            await self.uow.searches.save(search)
            await self.uow.commit()

        # 3. collecting
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            search.stage = SearchStage.COLLECTING
            await self.uow.searches.save(search)
            await self.uow.commit()

        with timed_stage(search_id, SearchStage.COLLECTING.value):
            await self._collect(search_id, analysis)

        # 4. scoring (по уже сохранённым постам)
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            search.stage = SearchStage.SCORING
            await self.uow.searches.save(search)
            await self.uow.commit()

        with timed_stage(search_id, SearchStage.SCORING.value):
            await self.scorer.score_search(search_id, analysis)

        # 5. grouping
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            search.stage = SearchStage.GROUPING
            await self.uow.searches.save(search)
            await self.uow.commit()

        with timed_stage(search_id, SearchStage.GROUPING.value):
            await self.scorer.group_search(search_id)

        # 6. finish
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            search.finish()
            await self.uow.searches.save(search)
            await self.uow.commit()

        # 7. готовая подборка → в кэш (B2-20); failed / cancelled не кэшируем
        if self.cache is not None and search.status in CACHEABLE_STATUSES:
            await self.cache.put(key_of(search), search.id)

    async def _analyze(self, search: Search) -> tuple[QueryAnalysis, str | None]:
        """→ (разбор, warning для поиска или None)."""
        try:
            analysis, degraded = await self.ml.analyze_query(search.query)
        except Exception as e:
            log.warning("analyze_query failed, degrading", error=str(e))
            return QueryAnalysis(
                query_type=QueryType.TOPIC.value,
                summary="Базовый поиск по фразе",
                search_queries=[search.query],
            ), "ML недоступен — использованы базовые фразы поиска"
        # degraded: ml_service ответил, но без моделей (эвристики). Переход ollama → yandex
        # degraded не даёт. ML_SHOW_DEGRADED_WARNING=false — не показываем и эвристики
        if degraded and self.show_degraded_warning:
            return analysis, "ML работал в упрощённом режиме"
        return analysis, None

    async def _collect(self, search_id: uuid.UUID, analysis: QueryAnalysis) -> list[TargetJob]:
        async with self.uow:
            search = _require(await self.uow.searches.get_with_targets(search_id), search_id)
            # при повторе (RetrySearch) завершённые цели не трогаем — только сброшенные в PENDING
            targets = [t for t in search.targets if not t.is_finished]

        jobs: list[TargetJob] = []
        tasks = [self._collect_target(search_id, t, analysis) for t in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for t, res in zip(targets, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("target collect crashed", target_id=str(t.id), error=str(res))
            else:
                jobs.append(res)
        return jobs

    async def _collect_target(
        self, search_id: uuid.UUID, target: SearchTarget, analysis: QueryAnalysis
    ) -> TargetJob:
        platform = _platform_title(target.platform)
        async with self.sem:
            async with self.uow:
                target = (await self.uow.targets.get_by_ids([target.id]))[0]
                target.start()
                await self.uow.targets.save(target)
                await self.uow.commit()

            try:
                with timed_stage(search_id, "target_collect", target_id=str(target.id)):
                    posts = await asyncio.wait_for(
                        self._call_collector(search_id, target, analysis),
                        timeout=self.target_timeout,
                    )
            except TimeoutError:
                await self._fail_target(
                    target.id, "TIMEOUT", ERROR_MESSAGES["TIMEOUT"].format(platform=platform)
                )
                return TargetJob(target=target, posts=[])
            except Exception as e:
                code = getattr(e, "code", "PLATFORM_UNAVAILABLE")
                # у ошибок соседа (UpstreamError) уже есть понятный текст для пользователя
                upstream_message = getattr(e, "message", "") if code != "TIMEOUT" else ""
                msg = upstream_message or ERROR_MESSAGES.get(code, f"{platform}: {e}").format(
                    platform=platform
                )
                await self._fail_target(target.id, code, msg)
                return TargetJob(target=target, posts=[])

            # сохраняем посты и сразу скорим их
            async with self.uow:
                search = _require(await self.uow.searches.get_with_targets(search_id), search_id)

            saved_results = await self.save.save_posts(search, target, posts)

            if not posts:
                async with self.uow:
                    target = (await self.uow.targets.get_by_ids([target.id]))[0]
                    target.mark_empty()
                    await self.uow.targets.save(target)
                    await self.uow.commit()
            else:
                async with self.uow:
                    target = (await self.uow.targets.get_by_ids([target.id]))[0]
                    # «в подборке» считается после оценки (recount_matched в ScoringHandler)
                    target.mark_done(fetched=len(posts), matched=0)
                    await self.uow.targets.save(target)
                    await self.uow.commit()

                # сразу скорим новые посты этой цели (конвейер)
                with timed_stage(search_id, "target_scoring", target_id=str(target.id)):
                    await self.scorer.score_results(search_id, [r.id for r in saved_results])

            return TargetJob(target=target, posts=posts)

    async def _call_collector(
        self, search_id: uuid.UUID, target: SearchTarget, analysis: QueryAnalysis
    ) -> list[RawPost]:
        async with self.uow:
            search = _require(await self.uow.searches.get_by_id(search_id), search_id)
            source = (
                await self.uow.sources.get_by_id(target.source_id) if target.source_id else None
            )
        if target.kind == "source":
            if source is None:
                raise CollectorError("SOURCE_NOT_FOUND", "Источник удалён из каталога")
            res = await self.collector.collect_from_source(
                platform=target.platform,
                # external_id площадки (у VK — числовой id группы), а не хвост ссылки
                source_external_id=source.external_id,
                start_utc=search.period.start_utc,
                end_utc=search.period.end_utc,
                keywords=analysis.search_queries,
                max_posts=0,  # 0 — лимит сборщика (DEFAULT_MAX_POSTS_SOURCE в compose)
            )
        else:
            res = await self.collector.search_platform(
                platform=target.platform,
                queries=analysis.search_queries,
                start_utc=search.period.start_utc,
                end_utc=search.period.end_utc,
                region_terms=["Красноярск", "Красноярский край"],
                max_posts=0,  # 0 — лимит сборщика (DEFAULT_MAX_POSTS_SEARCH в compose)
            )
        return res.posts

    async def _fail_target(self, target_id: uuid.UUID, code: str, message: str) -> None:
        async with self.uow:
            target = (await self.uow.targets.get_by_ids([target_id]))[0]
            target.mark_failed(code, message)
            await self.uow.targets.save(target)
            await self.uow.commit()

    async def _force_fail(self, search_id: uuid.UUID, message: str) -> None:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search or search.status in {
                SearchStatus.COMPLETED,
                SearchStatus.PARTIAL,
                SearchStatus.FAILED,
                SearchStatus.CANCELLED,
            }:
                return
            for t in search.targets:
                if not t.is_finished:
                    t.mark_failed("INTERNAL", message)
            search.status = SearchStatus.FAILED
            search.stage = SearchStage.DONE
            from search_service.domain.entities import utcnow

            search.finished_at = utcnow()
            await self.uow.searches.save(search)
            # цели, помеченные FAILED выше, тоже сохраняем
            for t in search.targets:
                await self.uow.targets.save(t)
            await self.uow.commit()

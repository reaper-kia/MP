"""Основной пайплайн поиска: analyzing → collecting → scoring → grouping."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, cast

import structlog

from search_service.applications.ports.collector_client import CollectorClient, RawPost
from search_service.applications.handlers.save import SaveHandler
from search_service.applications.handlers.scoring import ScoringHandler
from search_service.applications.ports.collector_client import CollectorClient
from search_service.applications.ports.ml_client import MlClient, QueryAnalysis
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import (
    DateStatus,
    SearchStage,
    SearchStatus,
    TargetStatus,
)

log = structlog.get_logger()

ERROR_MESSAGES: dict[str, str] = {
    "PLATFORM_UNAVAILABLE": "{platform} недоступна",
    "TIMEOUT": "{platform} не ответила за 60 секунд",
    "SOURCE_NOT_FOUND": "Источник не найден на площадке",
    "SOURCE_PRIVATE": "Группа закрыта",
    "RATE_LIMITED": "Превышен лимит запросов к площадке",
}


@dataclass
class TargetJob:
    target: SearchTarget
    posts: list[Any]


class Pipeline:
    def __init__(
        self,
        uow: UnitOfWork,
        collector: CollectorClient,
        ml: MlClient,
        semaphore: asyncio.Semaphore,
        target_timeout: int = 60,
    ) -> None:
        self.uow = uow
        self.collector = collector
        self.ml = ml
        self.sem = semaphore
        self.target_timeout = target_timeout
        self.save = SaveHandler(uow)
        self.scorer = ScoringHandler(uow, ml)

    async def run(self, search_id: uuid.UUID) -> None:
        try:
            await self._run_inner(search_id)
        except Exception as e:
            log.exception("pipeline crashed", search_id=str(search_id), error=str(e))
            await self._force_fail(search_id, f"Непредвиденная ошибка: {e}")

    async def _run_inner(self, search_id: uuid.UUID) -> None:
        # 1. старт
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.start()
            await self.uow.searches.save(search)
            await self.uow.commit()

        # 2. analyze query
        analysis, degraded = await self._analyze(search)
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.query_type = analysis.query_type
            search.query_analysis = {
                "query_type": analysis.query_type,
                "summary": analysis.summary,
                "search_queries": analysis.search_queries,
                "needs_clarification": analysis.needs_clarification,
                "clarification_hint": analysis.clarification_hint,
            }
            if degraded:
                search.add_warning("ML недоступен — использованы базовые фразы поиска")
            await self.uow.searches.save(search)
            await self.uow.commit()

        # 3. collecting
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.stage = SearchStage.COLLECTING
            await self.uow.searches.save(search)
            await self.uow.commit()

        jobs: list[TargetJob] = await self._collect(search_id, analysis)

        # 4. scoring
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.stage = SearchStage.SCORING
            await self.uow.searches.save(search)
            await self.uow.commit()

        await self.scorer.score_search(search_id, analysis)

        # B2-07: пересчёт matched после скоринга
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            for target in search.targets:
                if target.status == TargetStatus.DONE:
                    matched = await self.uow.results.count_matched_by_target(
                        search_id, target.id
                    )
                    target.matched = matched
                    await self.uow.targets.save(target)
            await self.uow.commit()

        # 5. grouping
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.stage = SearchStage.GROUPING
            await self.uow.searches.save(search)
            await self.uow.commit()

        await self.scorer.group_search(search_id)

        # 6. finish
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return
            search.finish()
            await self.uow.searches.save(search)
            await self.uow.commit()

    async def _analyze(self, search: Search) -> tuple[QueryAnalysis, bool]:
        try:
            return await self.ml.analyze_query(search.query)
        except Exception as e:
            log.warning("analyze_query failed, degrading", error=str(e))
            return QueryAnalysis(
                query_type="fallback",
                summary="Базовый поиск по фразе",
                search_queries=[search.query],
                needs_clarification=False,
                clarification_hint="",  # было None
            ), True

    async def _collect( self, search_id: uuid.UUID, analysis: QueryAnalysis) -> list[TargetJob]:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return []
            active_targets: list[SearchTarget] = list(search.targets)

        collected_jobs: list[TargetJob] = []
        coroutines = [self._collect_target(search_id, t, analysis) for t in active_targets]
        
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        for target, result in zip(active_targets, results):
            if isinstance(result, Exception):
                log.warning("target collect crashed", target_id=str(target.id), error=str(result))
            elif isinstance(result, TargetJob):
                collected_jobs.append(result)

        return collected_jobs
    
    async def _collect_target(
        self, search_id: uuid.UUID, target: SearchTarget, analysis: QueryAnalysis
    ) -> TargetJob:
        async with self.sem:
            async with self.uow:
                targets = await self.uow.targets.get_by_ids([target.id])
                target = targets[0]
                target.start()
                await self.uow.targets.save(target)
                await self.uow.commit()

            try:
                posts = await asyncio.wait_for(
                    self._call_collector(target, analysis),
                    timeout=self.target_timeout,
                )
            except asyncio.TimeoutError:
                await self._fail_target(
                    target.id,
                    "TIMEOUT",
                    ERROR_MESSAGES["TIMEOUT"].format(platform=target.platform),
                )
                return TargetJob(target=target, posts=[])
            except Exception as e:
                code = getattr(e, "code", "PLATFORM_UNAVAILABLE")
                # Текст ошибки коллектора доходит до пользователя как есть
                message = getattr(e, "message", None) or str(e)
                if not message:
                    message = ERROR_MESSAGES.get(
                        code, "{platform} недоступна"
                    ).format(platform=target.platform)
                await self._fail_target(target.id, code, message)
                return TargetJob(target=target, posts=[])

            async with self.uow:
                search = await self.uow.searches.get_with_targets(search_id)
                if not search:
                    return TargetJob(target=target, posts=[])

            saved_results = await self.save.save_posts(search, target, posts)

            if not posts:
                async with self.uow:
                    targets = await self.uow.targets.get_by_ids([target.id])
                    target = targets[0]
                    target.mark_empty()
                    await self.uow.targets.save(target)
                    await self.uow.commit()
            else:
                async with self.uow:
                    targets = await self.uow.targets.get_by_ids([target.id])
                    target = targets[0]
                    in_period = sum(
                        1 for r in saved_results if r.date_status == DateStatus.IN_PERIOD
                    )
                    target.mark_done(fetched=len(posts), matched=in_period)
                    await self.uow.targets.save(target)
                    await self.uow.commit()

                await self.scorer.score_results(search_id, [r.id for r in saved_results])

            return TargetJob(target=target, posts=posts)
        
    async def _call_collector(
        self, target: SearchTarget, analysis: QueryAnalysis
    ) -> list[RawPost]:
        search_id = cast(uuid.UUID, target.search_id)

        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                return []
            
            # Достаём external_id источника из каталога, а не из URL цели
            source_external_id = ""
            if target.source_id is not None:
                # Пытаемся через get_by_ids (стандартный метод)
                if hasattr(self.uow.sources, "get_by_ids"):
                    found = await self.uow.sources.get_by_ids([target.source_id])
                    if found:
                        source_external_id = found[0].external_id
                # Fallback: через get (если в фейке так называется)
                elif hasattr(self.uow.sources, "get"):
                    found = await self.uow.sources.get(target.source_id)
                    if found:
                        source_external_id = found.external_id
            
            # Если всё же не нашли в каталоге, берём хвост URL как последний шанс
            if not source_external_id and target.url:
                source_external_id = target.url.split("/")[-1]

        if target.kind == "source":
            res = await self.collector.collect_from_source(
                platform=target.platform,
                source_external_id=source_external_id,
                start_utc=search.period.start_utc,
                end_utc=search.period.end_utc,
                keywords=analysis.search_queries,
                max_posts=300,
            )
        else:
            res = await self.collector.search_platform(
                platform=target.platform,
                queries=analysis.search_queries,
                start_utc=search.period.start_utc,
                end_utc=search.period.end_utc,
                region_terms=["Красноярск", "Красноярский край"],
                max_posts=500,
            )
        return res.posts
    async def _fail_target(self, target_id: uuid.UUID, code: str, message: str) -> None:
        async with self.uow:
            targets = await self.uow.targets.get_by_ids([target_id])
            target = targets[0]
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
            await self.uow.commit()
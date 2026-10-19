from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import structlog

from search_service.applications.handlers.save import SaveHandler
from search_service.applications.handlers.scoring import ScoringHandler
from search_service.applications.ports.collector_client import CollectorClient
from search_service.applications.ports.ml_client import MlClient
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import DateStatus, SearchStage, SearchStatus

log = structlog.get_logger()

# русские сообщения об ошибках по коду
ERROR_MESSAGES = {
    "PLATFORM_UNAVAILABLE": "{platform} недоступна",
    "TIMEOUT": "{platform} не ответила за 60 секунд",
    "SOURCE_NOT_FOUND": "Источник не найден на площадке",
    "SOURCE_PRIVATE": "Группа закрыта",
    "RATE_LIMITED": "Превышен лимит запросов к площадке",
}


@dataclass
class TargetJob:
    target: SearchTarget
    posts: list


class Pipeline:
    """Основной пайплайн поиска: analyzing → collecting → scoring → grouping."""

    def __init__(
        self,
        uow: UnitOfWork,
        collector: CollectorClient,
        ml: MlClient,
        semaphore: asyncio.Semaphore,
        target_timeout: int = 60,
    ):
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
            search.stage = SearchStage.COLLECTING
            await self.uow.searches.save(search)
            await self.uow.commit()

        jobs = await self._collect(search_id, analysis)

        # 4. scoring (по уже сохранённым постам)
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            search.stage = SearchStage.SCORING
            await self.uow.searches.save(search)
            await self.uow.commit()

        await self.scorer.score_search(search_id, analysis)

        # 5. grouping
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            search.stage = SearchStage.GROUPING
            await self.uow.searches.save(search)
            await self.uow.commit()

        await self.scorer.group_search(search_id)

        # 6. finish
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            search.finish()
            await self.uow.searches.save(search)
            await self.uow.commit()

    async def _analyze(self, search: Search):
        try:
            return await self.ml.analyze_query(search.query)
        except Exception as e:
            log.warning("analyze_query failed, degrading", error=str(e))
            from search_service.applications.ports.ml_client import QueryAnalysis

            return QueryAnalysis(
                query_type="fallback",
                summary="Базовый поиск по фразе",
                search_queries=[search.query],
            ), True

    async def _collect(self, search_id: uuid.UUID, analysis) -> list[TargetJob]:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            targets = list(search.targets)

        jobs: list[TargetJob] = []
        tasks = [self._collect_target(search_id, t, analysis) for t in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for t, res in zip(targets, results):
            if isinstance(res, Exception):
                log.warning("target collect crashed", target_id=str(t.id), error=str(res))
            else:
                jobs.append(res)
        return jobs

    async def _collect_target(
        self, search_id: uuid.UUID, target: SearchTarget, analysis
    ) -> TargetJob:
        async with self.sem:
            async with self.uow:
                target = await self.uow.targets.get_by_ids([target.id])
                target = target[0]
                target.start()
                await self.uow.targets.save(target)
                await self.uow.commit()

            try:
                posts = await asyncio.wait_for(
                    self._call_collector(target, analysis),
                    timeout=self.target_timeout,
                )
            except TimeoutError:
                await self._fail_target(
                    target.id, "TIMEOUT", ERROR_MESSAGES["TIMEOUT"].format(platform=target.platform)
                )
                return TargetJob(target=target, posts=[])
            except Exception as e:
                code = getattr(e, "code", "PLATFORM_UNAVAILABLE")
                msg = ERROR_MESSAGES.get(code, f"{target.platform}: {e}").format(
                    platform=target.platform
                )
                await self._fail_target(target.id, code, msg)
                return TargetJob(target=target, posts=[])

            # сохраняем посты и сразу скорим их
            async with self.uow:
                search = await self.uow.searches.get_with_targets(search_id)

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
                    in_period = sum(
                        1 for r in saved_results if r.date_status == DateStatus.IN_PERIOD
                    )
                    target.mark_done(fetched=len(posts), matched=in_period)
                    await self.uow.targets.save(target)
                    await self.uow.commit()

                # сразу скорим новые посты этой цели (конвейер)
                await self.scorer.score_results(search_id, [r.id for r in saved_results])

            return TargetJob(target=target, posts=posts)

    async def _call_collector(self, target: SearchTarget, analysis):
        async with self.uow:
            search = await self.uow.searches.get(search_id := target.search_id)
        if target.kind == "source":
            res = await self.collector.collect_from_source(
                platform=target.platform,
                source_external_id=target.url.split("/")[-1] if target.url else "",
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

    async def _fail_target(self, target_id: uuid.UUID, code: str, message: str):
        async with self.uow:
            target = (await self.uow.targets.get_by_ids([target_id]))[0]
            target.mark_failed(code, message)
            await self.uow.targets.save(target)
            await self.uow.commit()

    async def _force_fail(self, search_id: uuid.UUID, message: str):
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

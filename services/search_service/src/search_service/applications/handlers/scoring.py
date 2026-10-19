from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from itertools import islice
from typing import Any

import structlog

from search_service.applications.handlers.matched import recount_matched
from search_service.applications.ports.ml_client import (
    MlClient,
    PostForScoring,
    PostGroup,
    QueryAnalysis,
)
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import Publication, Search, SearchResult
from search_service.domain.enums import QueryType, Relevance, SearchMode
from search_service.domain.errors import NotFoundError

log = structlog.get_logger()

# контракт ml.v1 GroupPosts: до 500 постов за вызов
GROUP_POSTS_LIMIT = 500

NO_REGION_EXPLANATION = (
    "Нет связи с Красноярским краем: источник не региональный и в тексте край не упоминается"
)


def analysis_to_dict(analysis: QueryAnalysis) -> dict[str, Any]:
    return {
        "query_type": str(analysis.query_type),
        "summary": analysis.summary,
        "search_queries": list(analysis.search_queries),
        "entities": list(analysis.entities),
        "must_concepts": list(analysis.must_concepts),
        "exclude_concepts": list(analysis.exclude_concepts),
        "needs_clarification": analysis.needs_clarification,
        "clarification_hint": analysis.clarification_hint,
    }


def analysis_from_dict(qa: dict[str, Any]) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=str(qa.get("query_type", QueryType.TOPIC.value)),
        summary=str(qa.get("summary", "")),
        search_queries=list(qa.get("search_queries", [])),
        entities=list(qa.get("entities", [])),
        must_concepts=list(qa.get("must_concepts", [])),
        exclude_concepts=list(qa.get("exclude_concepts", [])),
        needs_clarification=bool(qa.get("needs_clarification", False)),
        clarification_hint=str(qa.get("clarification_hint", "")),
    )


class ScoringHandler:
    def __init__(
        self, uow: UnitOfWork, ml: MlClient, batch_size: int = 30, max_concurrent: int = 3
    ) -> None:
        self.uow = uow
        self.ml = ml
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self._sem = asyncio.Semaphore(max_concurrent)

    async def score_search(self, search_id: uuid.UUID, analysis: QueryAnalysis) -> None:
        """Скорит все relevance IS NULL в поиске."""
        async with self.uow:
            results = await self.uow.results.get_by_search(search_id)
            pending = [r for r in results if r.relevance is None]
            pub_ids = [r.publication_id for r in pending]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}

            async with self.uow:
                search = await self.uow.searches.get_by_id(search_id)
            if search is None:
                raise NotFoundError("SEARCH_NOT_FOUND")

        batches = list(self._chunks(pending, self.batch_size))
        sem = self._sem

        async def process_batch(batch: list[SearchResult]) -> None:
            async with sem:
                await self._score_batch(search, analysis, batch, pubs_by_id)

        try:
            await asyncio.gather(*(process_batch(b) for b in batches))
        finally:
            await recount_matched(self.uow, search_id, {r.target_id for r in pending})

    async def score_results(self, search_id: uuid.UUID, result_ids: list[uuid.UUID]) -> None:
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
            if search is None:
                raise NotFoundError("SEARCH_NOT_FOUND")
            results = [
                r for r in await self.uow.results.get_by_search(search_id) if r.id in result_ids
            ]
            pub_ids = [r.publication_id for r in results]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}
            analysis: QueryAnalysis | None = None
            if search.query_analysis:
                analysis = analysis_from_dict(search.query_analysis)

        if not analysis:
            analysis, _ = await self.ml.analyze_query(search.query)

        batches = list(self._chunks(results, self.batch_size))
        sem = self._sem

        async def process_batch(batch: list[SearchResult]) -> None:
            async with sem:
                await self._score_batch(search, analysis, batch, pubs_by_id)

        try:
            await asyncio.gather(*(process_batch(b) for b in batches))
        finally:
            await recount_matched(self.uow, search_id, {r.target_id for r in results})

    async def _score_batch(
        self,
        search: Search,
        analysis: QueryAnalysis,
        batch: list[SearchResult],
        pubs_by_id: dict[uuid.UUID, Publication],
    ) -> None:
        posts_for_scoring: list[PostForScoring] = []
        for r in batch:
            pub = pubs_by_id.get(r.publication_id)
            if not pub:
                continue
            posts_for_scoring.append(
                PostForScoring(
                    id=str(r.id),
                    title=pub.title,
                    text=pub.text,
                    source_name=pub.source_name,
                    source_is_regional=r.region_by_source,
                )
            )

        try:
            scores, degraded = await asyncio.wait_for(
                self.ml.score_posts(query=search.query, analysis=analysis, posts=posts_for_scoring),
                timeout=60,
            )
        except Exception as e:
            log.warning("ml batch failed, marking disputed", error=str(e))
            async with self.uow:
                for r in batch:
                    r.set_score(
                        relevance=Relevance.DISPUTED,
                        score=0.0,
                        explanation="Не удалось проверить автоматически — проверьте вручную",
                        region_by_content=False,
                        region_evidence="",
                        sentiment=None,
                        excerpt_start=0,
                        excerpt_end=min(300, len(pubs_by_id[r.publication_id].text)),
                        highlights=[],
                    )
                    await self.uow.results.save(r)
                await self.uow.commit()
            return

        scores_by_id = {s.id: s for s in scores}
        async with self.uow:
            for r in batch:
                s = scores_by_id.get(str(r.id))
                if not s:
                    continue
                pub = pubs_by_id[r.publication_id]
                text_len = len(pub.text)

                # валидация excerpt_span
                ex_start, ex_end = None, None
                if s.excerpt_span:
                    a, b = s.excerpt_span
                    if 0 <= a < b <= text_len:
                        ex_start, ex_end = a, b
                if ex_start is None:
                    ex_start, ex_end = 0, min(300, text_len)

                # валидация highlights
                highlights: list[list[int]] = []
                for span in s.highlight_spans:
                    a, b = span
                    if 0 <= a < b <= text_len:
                        highlights.append([a, b])

                try:
                    rel = Relevance(s.relevance)
                except ValueError:
                    rel = Relevance.DISPUTED

                explanation = s.explanation
                if (
                    search.mode is SearchMode.GLOBAL
                    and rel is not Relevance.IRRELEVANT
                    and not r.region_by_source
                    and not s.region_by_content
                ):
                    # «везде»: без привязки к краю по источнику и по тексту — отсеиваем
                    rel = Relevance.IRRELEVANT
                    explanation = NO_REGION_EXPLANATION

                r.set_score(
                    relevance=rel,
                    score=s.score,
                    explanation=explanation,
                    region_by_content=s.region_by_content,
                    region_evidence=s.region_evidence,
                    sentiment=s.sentiment,
                    excerpt_start=ex_start,
                    excerpt_end=ex_end,
                    highlights=highlights,
                )
                await self.uow.results.save(r)
            await self.uow.commit()

    async def group_search(self, search_id: uuid.UUID) -> None:
        async with self.uow:
            results = await self.uow.results.get_by_search(search_id)
            passed = [
                r
                for r in results
                if r.relevance in {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED}
            ]
            pub_ids = [r.publication_id for r in passed]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}

        if not passed:
            return

        # рядом по времени — вероятнее копии одного сюжета: при нарезке чаще окажутся в одном куске
        passed.sort(
            key=lambda r: (
                pubs_by_id[r.publication_id].published_at is None,
                pubs_by_id[r.publication_id].published_at or datetime.min.replace(tzinfo=UTC),
            )
        )
        prefix = str(search_id)[:8]
        for idx, chunk in enumerate(self._chunks(passed, GROUP_POSTS_LIMIT)):
            posts_for_group: list[dict[str, Any]] = [
                {
                    "id": str(r.id),
                    "title": pubs_by_id[r.publication_id].title,
                    "text": pubs_by_id[r.publication_id].text,
                }
                for r in chunk
            ]
            try:
                groups = await self.ml.group_posts(posts_for_group)
            except Exception as e:
                log.warning("group_posts failed", chunk=idx, error=str(e))
                # без групп — не критично; остальные куски группируем
                continue
            # group_id у ML уникален в пределах вызова → у каждого следующего куска свой префикс
            chunk_prefix = prefix if idx == 0 else f"{prefix}-{idx}"
            await self._save_groups(search_id, chunk_prefix, groups)

    async def _save_groups(
        self, search_id: uuid.UUID, prefix: str, groups: list[PostGroup]
    ) -> None:
        async with self.uow:
            # пересчитываем results, чтобы они были актуальны
            fresh_results = await self.uow.results.get_by_search(search_id)
            by_id = {str(r.id): r for r in fresh_results}
            for g in groups:
                full_group_id = f"{prefix}-{g.group_id}"
                for pid in g.post_ids:
                    r = by_id.get(pid)
                    if r:
                        r.set_group(full_group_id)
                        await self.uow.results.save(r)
            await self.uow.commit()

    @staticmethod
    def _chunks[T](seq: Iterable[T], size: int) -> Iterator[list[T]]:
        it = iter(seq)
        while chunk := list(islice(it, size)):
            yield chunk

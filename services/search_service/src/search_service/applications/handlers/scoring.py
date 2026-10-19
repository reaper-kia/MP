from __future__ import annotations

import asyncio
import uuid
from itertools import islice

import structlog

from search_service.applications.ports.ml_client import MlClient, PostForScoring
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.enums import Relevance

log = structlog.get_logger()


class ScoringHandler:
    def __init__(
        self, uow: UnitOfWork, ml: MlClient, batch_size: int = 30, max_concurrent: int = 3
    ):
        self.uow = uow
        self.ml = ml
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self._sem = asyncio.Semaphore(max_concurrent)

    async def score_search(self, search_id: uuid.UUID, analysis) -> None:
        """Скорит все relevance IS NULL в поиске."""
        async with self.uow:
            results = await self.uow.results.get_by_search(search_id)
            pending = [r for r in results if r.relevance is None]
            pub_ids = [r.publication_id for r in pending]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}

            async with self.uow:
                search = await self.uow.searches.get(search_id)

        batches = list(self._chunks(pending, self.batch_size))
        sem = self._sem

        async def process_batch(batch):
            async with sem:
                await self._score_batch(search, analysis, batch, pubs_by_id)

        await asyncio.gather(*(process_batch(b) for b in batches))

    async def score_results(self, search_id: uuid.UUID, result_ids: list[uuid.UUID]) -> None:
        async with self.uow:
            search = await self.uow.searches.get(search_id)
            results = [
                r for r in await self.uow.results.get_by_search(search_id) if r.id in result_ids
            ]
            pub_ids = [r.publication_id for r in results]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}
            analysis = None
            if search.query_analysis:
                from search_service.applications.ports.ml_client import QueryAnalysis

                qa = search.query_analysis
                analysis = QueryAnalysis(
                    query_type=qa.get("query_type", "unknown"),
                    summary=qa.get("summary", ""),
                    search_queries=qa.get("search_queries", []),
                )

        if not analysis:
            from search_service.applications.ports.ml_client import QueryAnalysis

            analysis, _ = await self.ml.analyze_query(search.query)

        batches = list(self._chunks(results, self.batch_size))
        sem = self._sem

        async def process_batch(batch):
            async with sem:
                await self._score_batch(search, analysis, batch, pubs_by_id)

        await asyncio.gather(*(process_batch(b) for b in batches))

    async def _score_batch(self, search, analysis, batch, pubs_by_id):
        posts_for_scoring = []
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
                highlights = []
                for span in s.highlight_spans:
                    a, b = span
                    if 0 <= a < b <= text_len:
                        highlights.append([a, b])

                try:
                    rel = Relevance(s.relevance)
                except ValueError:
                    rel = Relevance.DISPUTED

                r.set_score(
                    relevance=rel,
                    score=s.score,
                    explanation=s.explanation,
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

        posts_for_group = [
            {
                "id": str(r.id),
                "title": pubs_by_id[r.publication_id].title,
                "text": pubs_by_id[r.publication_id].text,
            }
            for r in passed
        ]
        try:
            groups = await self.ml.group_posts(posts_for_group)
        except Exception as e:
            log.warning("group_posts failed", error=str(e))
            # без групп — не критично
            return

        async with self.uow:
            # пересчитываем results, чтобы они были актуальны
            fresh_results = await self.uow.results.get_by_search(search_id)
            by_id = {str(r.id): r for r in fresh_results}
            prefix = str(search_id)[:8]
            for g in groups:
                full_group_id = f"{prefix}-{g.group_id}"
                for pid in g.post_ids:
                    r = by_id.get(pid)
                    if r:
                        r.set_group(full_group_id)
                        await self.uow.results.save(r)
            await self.uow.commit()

    @staticmethod
    def _chunks(seq, size):
        it = iter(seq)
        while chunk := list(islice(it, size)):
            yield chunk

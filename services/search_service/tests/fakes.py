"""Фейки портов: хэндлеры тестируются без БД и без соседей (как в шаблоне)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from search_service.applications.exceptions import UpstreamError
from search_service.applications.ports.collector_client import CollectResult, RawPost, SourceInfo
from search_service.applications.ports.ml_client import (
    PostForScoring,
    PostGroup,
    PostScore,
    QueryAnalysis,
)
from search_service.applications.request_context import current_request_id
from search_service.domain.entities import Publication, Search, SearchResult, SearchTarget, Source
from search_service.domain.enums import DateStatus, QueryType, Relevance


class InMemorySources:
    def __init__(self):
        self.store: dict[uuid.UUID, Source] = {}

    async def get_by_id(self, i):
        return self.store.get(i)

    async def get_by_key(self, p, e):
        for s in self.store.values():
            if s.platform == p and s.external_id == e and s.is_alive:
                return s
        return None

    async def get_by_ids(self, ids):
        return [self.store[i] for i in ids if i in self.store]

    async def list(self, **kw):
        items = [s for s in self.store.values() if s.is_alive]
        if kw.get("platforms"):
            items = [s for s in items if s.platform in kw["platforms"]]
        if kw.get("is_active") is not None:
            items = [s for s in items if s.is_active == kw["is_active"]]
        return items, len(items)

    async def add(self, e):
        self.store[e.id] = e

    async def save(self, e):
        self.store[e.id] = e


class InMemorySearches:
    def __init__(self):
        self.store: dict[uuid.UUID, Search] = {}

    async def get_by_id(self, i):
        return self.store.get(i)

    async def get_with_targets(self, i):
        return self.store.get(i)

    async def list(self, **kw):
        items = list(self.store.values())
        return items, len(items), False

    async def list_running_or_queued(self):
        return [s for s in self.store.values() if s.status in {"queued", "running"}]

    async def add(self, e):
        self.store[e.id] = e

    async def save(self, e):
        self.store[e.id] = e


class InMemoryTargets:
    def __init__(self):
        self.store: dict[uuid.UUID, SearchTarget] = {}

    async def list_by_search(self, sid):
        return [t for t in self.store.values() if t.search_id == sid]

    async def add(self, e):
        self.store[e.id] = e

    async def save(self, e):
        self.store[e.id] = e

    async def get_by_ids(self, ids):
        return [self.store[i] for i in ids if i in self.store]

    async def set_matched(self, target_id, matched):
        self.store[target_id].matched = matched


class InMemoryPublications:
    def __init__(self):
        self.store: dict[uuid.UUID, Publication] = {}

    async def get_by_key(self, p, s, post):
        for pub in self.store.values():
            if pub.platform == p and pub.source_external_id == s and pub.post_external_id == post:
                return pub
        return None

    async def get_by_ids(self, ids):
        return [self.store[i] for i in ids if i in self.store]

    async def upsert(self, e):
        existing = await self.get_by_key(e.platform, e.source_external_id, e.post_external_id)
        if existing:
            existing.merge_from(e)
            return existing
        self.store[e.id] = e
        return e


class InMemoryResults:
    def __init__(self):
        self.store: dict[uuid.UUID, SearchResult] = {}

    async def add(self, e):
        self.store[e.id] = e

    async def save(self, e):
        self.store[e.id] = e

    async def get_by_search(self, sid):
        return [r for r in self.store.values() if r.search_id == sid]

    async def list_filtered(self, **kw):
        items = [
            r
            for r in self.store.values()
            if r.search_id == kw["search_id"] and r.relevance is not None
        ]
        return items, len(items), False

    async def counts(self, sid):
        items = [r for r in self.store.values() if r.search_id == sid]
        return {
            "total": sum(
                1
                for r in items
                if r.relevance in {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED}
                and not r.excluded
            ),
            "direct": sum(1 for r in items if r.relevance == Relevance.DIRECT and not r.excluded),
            "indirect": sum(
                1 for r in items if r.relevance == Relevance.INDIRECT and not r.excluded
            ),
            "disputed": sum(
                1 for r in items if r.relevance == Relevance.DISPUTED and not r.excluded
            ),
            "rejected": sum(1 for r in items if r.relevance == Relevance.IRRELEVANT),
            "excluded": sum(1 for r in items if r.excluded),
            "unknown_date": sum(
                1
                for r in items
                if r.relevance in {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED}
                and not r.excluded
                and r.date_status == DateStatus.UNKNOWN
            ),
            "groups": len({r.group_id for r in items if r.group_id}),
        }

    async def exists_in_search(self, sid, pid):
        return any(r.search_id == sid and r.publication_id == pid for r in self.store.values())


class InMemoryUoW:
    def __init__(self):
        self.sources = InMemorySources()
        self.searches = InMemorySearches()
        self.targets = InMemoryTargets()
        self.publications = InMemoryPublications()
        self.results = InMemoryResults()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


# --- фейки портов соседей (applications/ports/collector_client.py, ml_client.py) ---


class FakeCollector:
    """sources[url] — что вернёт resolve; posts[(platform, external_id)] — посты источника;
    failing — source_external_id → код ошибки."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceInfo] = {}
        self.posts: dict[tuple[str, str], list[RawPost]] = {}
        self.search_posts: dict[str, list[RawPost]] = {}
        self.failing: dict[str, str] = {}
        self.calls: list[str] = []
        self.request_ids: list[str] = []  # request_id в момент каждого вызова (B2-12)
        self.delay = 0.0  # секунды на сбор — для отмены «на лету»

    async def resolve_source(self, url: str) -> SourceInfo:
        self.calls.append(f"resolve:{url}")
        if url not in self.sources:
            raise UpstreamError("collector", "SOURCE_NOT_FOUND", "Источник не найден")
        return self.sources[url]

    async def collect_from_source(
        self,
        *,
        platform: str,
        source_external_id: str,
        start_utc: datetime,
        end_utc: datetime,
        keywords: list[str],
        max_posts: int = 300,
    ) -> CollectResult:
        self.calls.append(f"collect:{platform}:{source_external_id}")
        self.request_ids.append(current_request_id())
        await asyncio.sleep(self.delay)
        if source_external_id in self.failing:
            code = self.failing[source_external_id]
            raise UpstreamError("collector", code, f"тестовая ошибка {code}")
        return CollectResult(posts=list(self.posts.get((platform, source_external_id), [])))

    async def search_platform(
        self,
        *,
        platform: str,
        queries: list[str],
        start_utc: datetime,
        end_utc: datetime,
        region_terms: list[str],
        max_posts: int = 500,
    ) -> CollectResult:
        self.calls.append(f"search:{platform}")
        return CollectResult(posts=list(self.search_posts.get(platform, [])))


class FakeMl:
    """По умолчанию всё DIRECT; relevance_by_text — подстрока текста → класс."""

    def __init__(self) -> None:
        self.relevance_by_text: dict[str, Relevance] = {}
        self.region_texts: set[str] = set()  # подстрока текста → region.by_content = True
        self.excerpt_span: tuple[int, int] | None = None  # None — «весь текст до 300»
        self.unavailable = False
        self.group_calls: list[int] = []  # размеры вызовов GroupPosts
        self.request_ids: list[str] = []  # request_id в момент каждого вызова (B2-12)

    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]:
        if self.unavailable:
            raise UpstreamError("ml", "ML_UNAVAILABLE", "ml недоступен")
        return QueryAnalysis(QueryType.TOPIC.value, f"Тема: {query}", [query]), False

    async def score_posts(
        self, *, query: str, analysis: QueryAnalysis, posts: list[PostForScoring]
    ) -> tuple[list[PostScore], bool]:
        self.request_ids.append(current_request_id())
        if self.unavailable:
            raise UpstreamError("ml", "ML_UNAVAILABLE", "ml недоступен")
        scores = []
        for p in posts:
            relevance = next(
                (r for needle, r in self.relevance_by_text.items() if needle in p.text),
                Relevance.DIRECT,
            )
            scores.append(
                PostScore(
                    id=p.id,
                    relevance=relevance.value,
                    score=0.9,
                    explanation="тест",
                    region_by_content=any(needle in p.text for needle in self.region_texts),
                    excerpt_span=self.excerpt_span or (0, min(len(p.text), 300)),
                    highlight_spans=[(0, 5)],
                )
            )
        return scores, False

    async def group_posts(self, posts: list[dict[str, Any]]) -> list[PostGroup]:
        self.group_calls.append(len(posts))
        return [PostGroup(f"g{i}", [p["id"]], p["id"]) for i, p in enumerate(posts, start=1)]


class FakeRunner:
    """SearchRunner без фона: запоминает, что запускали."""

    def __init__(self) -> None:
        self.launched: list[uuid.UUID] = []
        self.cancelled: list[uuid.UUID] = []

    async def launch(self, search_id: uuid.UUID) -> None:
        self.launched.append(search_id)

    async def cancel(self, search_id: uuid.UUID) -> None:
        self.cancelled.append(search_id)

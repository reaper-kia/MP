"""Фейки портов: хэндлеры тестируются без БД и без соседей (как в шаблоне)."""
from __future__ import annotations
import uuid

from search_service.domain.entities import Source, Search, SearchTarget, Publication, SearchResult
from search_service.domain.enums import Relevance
from collections.abc import Sequence
from types import TracebackType
from typing import Self

from search_service.applications.context import RequestContext
from search_service.applications.exceptions import UpstreamError
from search_service.applications.ports.collector import (
    CollectResult,
    PlatformInfo,
    RawPost,
    SourceInfo,
)
from search_service.applications.ports.ml import (
    PostForGrouping,
    PostForScoring,
    PostGroup,
    PostScore,
    QueryAnalysis,
    TextSpan,
)
from search_service.domain.enums import Platform, QueryType, Relevance
from search_service.domain.value_objects import UtcPeriod


class InMemorySources:
    def __init__(self): self.store: dict[uuid.UUID, Source] = {}
    async def get_by_id(self, i): return self.store.get(i)
    async def get_by_key(self, p, e):
        for s in self.store.values():
            if s.platform == p and s.external_id == e and s.is_alive: return s
        return None
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]
    async def list(self, **kw): items = [s for s in self.store.values() if s.is_alive]; return items, len(items)
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e


class InMemorySearches:
    def __init__(self): self.store: dict[uuid.UUID, Search] = {}
    async def get_by_id(self, i): return self.store.get(i)
    async def get_with_targets(self, i): return self.store.get(i)
    async def list(self, **kw): items = list(self.store.values()); return items, len(items), False
    async def list_running_or_queued(self):
        return [s for s in self.store.values() if s.status in {"queued", "running"}]
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e


class InMemoryTargets:
    def __init__(self): self.store: dict[uuid.UUID, SearchTarget] = {}
    async def list_by_search(self, sid): return [t for t in self.store.values() if t.search_id == sid]
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]


class InMemoryPublications:
    def __init__(self): self.store: dict[uuid.UUID, Publication] = {}
    async def get_by_key(self, p, s, post):
        for pub in self.store.values():
            if pub.platform == p and pub.source_external_id == s and pub.post_external_id == post:
                return pub
        return None
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]
    async def upsert(self, e):
        existing = await self.get_by_key(e.platform, e.source_external_id, e.post_external_id)
        if existing:
            existing.merge_from(e)
            return existing
        self.store[e.id] = e
        return e


class InMemoryResults:
    def __init__(self): self.store: dict[uuid.UUID, SearchResult] = {}
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e
    async def get_by_search(self, sid): return [r for r in self.store.values() if r.search_id == sid]
    async def list_filtered(self, **kw):
        items = [r for r in self.store.values() if r.search_id == kw["search_id"] and r.relevance is not None]
        return items, len(items), False
    async def counts(self, sid):
        items = [r for r in self.store.values() if r.search_id == sid]
        return {
            "total": sum(1 for r in items if r.relevance in {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED} and not r.excluded),
            "direct": sum(1 for r in items if r.relevance == Relevance.DIRECT and not r.excluded),
            "indirect": sum(1 for r in items if r.relevance == Relevance.INDIRECT and not r.excluded),
            "disputed": sum(1 for r in items if r.relevance == Relevance.DISPUTED and not r.excluded),
            "rejected": sum(1 for r in items if r.relevance == Relevance.IRRELEVANT),
            "excluded": sum(1 for r in items if r.excluded),
            "unknown_date": 0,
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
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def commit(self): pass
    async def rollback(self): pass


# --- фейки портов gRPC-клиентов (из main) для test_wiring ---


class FakeUnitOfWork:
    """TODO(B2-01): добавить in-memory репозитории (sources, searches, ...) по портам."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeCollector:
    """posts[(platform, external_id)] — что вернёт источник; failing — какие источники падают."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceInfo] = {}
        self.posts: dict[tuple[Platform, str], list[RawPost]] = {}
        self.search_posts: dict[Platform, list[RawPost]] = {}
        self.failing: dict[str, str] = {}  # source_external_id → error code
        self.calls: list[str] = []

    async def get_platforms(self, ctx: RequestContext) -> list[PlatformInfo]:
        return [PlatformInfo(p, p.value, True, p is not Platform.NEWS, "ok", "") for p in Platform]

    async def resolve_source(self, ctx: RequestContext, url: str) -> SourceInfo:
        self.calls.append(f"resolve:{url}")
        if url not in self.sources:
            raise UpstreamError("collector", "SOURCE_NOT_FOUND", "Источник не найден")
        return self.sources[url]

    async def collect_from_source(
        self,
        ctx: RequestContext,
        platform: Platform,
        source_external_id: str,
        period: UtcPeriod,
        keywords: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult:
        self.calls.append(f"collect:{platform}:{source_external_id}")
        if source_external_id in self.failing:
            code = self.failing[source_external_id]
            raise UpstreamError("collector", code, f"тестовая ошибка {code}")
        return CollectResult(posts=list(self.posts.get((platform, source_external_id), [])))

    async def search_platform(
        self,
        ctx: RequestContext,
        platform: Platform,
        queries: Sequence[str],
        period: UtcPeriod,
        region_terms: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult:
        self.calls.append(f"search:{platform}")
        return CollectResult(posts=list(self.search_posts.get(platform, [])))


class FakeMl:
    """По умолчанию всё DIRECT; relevance_by_text — подстрока текста → класс."""

    def __init__(self) -> None:
        self.relevance_by_text: dict[str, Relevance] = {}
        self.unavailable = False

    async def analyze_query(self, ctx: RequestContext, query: str) -> tuple[QueryAnalysis, bool]:
        if self.unavailable:
            raise UpstreamError("ml", "ML_UNAVAILABLE", "ml недоступен")
        return QueryAnalysis(QueryType.TOPIC, f"Тема: {query}", [query]), False

    async def score_posts(
        self,
        ctx: RequestContext,
        query: str,
        analysis: QueryAnalysis,
        posts: list[PostForScoring],
    ) -> tuple[list[PostScore], bool]:
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
                    relevance=relevance,
                    score=0.9,
                    explanation="тест",
                    region_by_content=False,
                    region_evidence="",
                    sentiment=None,
                    excerpt_span=TextSpan(0, min(len(p.text), 300)),
                    highlight_spans=[],
                )
            )
        return scores, False

    async def group_posts(
        self, ctx: RequestContext, posts: list[PostForGrouping]
    ) -> list[PostGroup]:
        return [PostGroup(f"g{i}", [p.id], p.id) for i, p in enumerate(posts, start=1)]

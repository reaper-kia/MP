"""Фейки портов: хэндлеры тестируются без БД и без соседей (как в шаблоне)."""

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

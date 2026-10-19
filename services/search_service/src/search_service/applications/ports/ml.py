"""Порт к ml_service. Реализация — infra/clients/ml_client.py, фейк — tests/fakes.py."""

from dataclasses import dataclass, field
from typing import Protocol

from search_service.applications.context import RequestContext
from search_service.domain.enums import QueryType, Relevance, Sentiment


@dataclass(frozen=True, slots=True)
class Entity:
    text: str
    type: str  # person | organization | location | event | date | number


@dataclass(frozen=True, slots=True)
class QueryAnalysis:
    """Полный разбор запроса. Хранить целиком (searches.query_analysis jsonb): нужен ScorePosts."""

    query_type: QueryType
    summary: str
    search_queries: list[str]
    entities: list[Entity] = field(default_factory=list)
    must_concepts: list[str] = field(default_factory=list)
    exclude_concepts: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_hint: str = ""


@dataclass(frozen=True, slots=True)
class PostForScoring:
    id: str  # search_results.id
    text: str
    title: str | None = None
    source_name: str = ""
    source_is_regional: bool = False


@dataclass(frozen=True, slots=True)
class TextSpan:
    """[start, end) в символах Python-строки publications.text."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class PostScore:
    id: str
    relevance: Relevance
    score: float
    explanation: str
    region_by_content: bool
    region_evidence: str
    sentiment: Sentiment | None
    excerpt_span: TextSpan | None
    highlight_spans: list[TextSpan]


@dataclass(frozen=True, slots=True)
class PostForGrouping:
    id: str
    text: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class PostGroup:
    group_id: str
    post_ids: list[str]
    representative_post_id: str


class MlClient(Protocol):
    async def analyze_query(self, ctx: RequestContext, query: str) -> tuple[QueryAnalysis, bool]:
        """→ (разбор, degraded)."""
        ...

    async def score_posts(
        self,
        ctx: RequestContext,
        query: str,
        analysis: QueryAnalysis,
        posts: list[PostForScoring],
    ) -> tuple[list[PostScore], bool]:
        """≤ 50 постов за вызов. → (оценки в том же порядке, degraded)."""
        ...

    async def group_posts(
        self, ctx: RequestContext, posts: list[PostForGrouping]
    ) -> list[PostGroup]: ...

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class QueryAnalysis:
    query_type: str
    summary: str
    search_queries: list[str] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    must_concepts: list[str] = field(default_factory=list)
    exclude_concepts: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_hint: str = ""


@dataclass
class PostForScoring:
    id: str
    title: str | None
    text: str
    source_name: str
    source_is_regional: bool


@dataclass
class PostScore:
    id: str
    relevance: str  # direct|indirect|disputed|irrelevant
    score: float
    explanation: str
    region_by_content: bool = False
    region_evidence: str = ""
    sentiment: str | None = None
    excerpt_span: tuple[int, int] | None = None
    highlight_spans: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class PostGroup:
    group_id: str
    post_ids: list[str]
    representative_post_id: str


class MlClient(Protocol):
    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]: ...
    async def score_posts(
        self, *, query: str, analysis: QueryAnalysis, posts: list[PostForScoring]
    ) -> tuple[list[PostScore], bool]: ...
    async def group_posts(self, posts: list[dict[str, Any]]) -> list[PostGroup]: ...

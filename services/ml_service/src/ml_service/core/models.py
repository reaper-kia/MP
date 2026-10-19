"""Зеркало контракта ml.v1. Proto ⇄ эти типы — только в transport/grpc/mappers.py."""

from dataclasses import dataclass, field
from enum import StrEnum


class QueryType(StrEnum):
    TOPIC = "topic"
    EVENT = "event"
    PERSON = "person"
    NEWS_TEXT = "news_text"


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    DATE = "date"
    NUMBER = "number"


class Relevance(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    DISPUTED = "disputed"
    IRRELEVANT = "irrelevant"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class Entity:
    text: str
    type: EntityType


@dataclass(frozen=True, slots=True)
class QueryAnalysis:
    query_type: QueryType
    summary: str
    search_queries: list[str]
    entities: list[Entity] = field(default_factory=list)
    must_concepts: list[str] = field(default_factory=list)
    exclude_concepts: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_hint: str = ""


@dataclass(frozen=True, slots=True)
class Post:
    """PostForScoring."""

    id: str
    text: str
    title: str | None = None
    source_name: str = ""
    source_is_regional: bool = False


@dataclass(frozen=True, slots=True)
class Span:
    """[start, end) в символах Python-строки Post.text."""

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
    excerpt_span: Span
    highlight_spans: list[Span]


@dataclass(frozen=True, slots=True)
class GroupInput:
    """PostForGrouping."""

    id: str
    text: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class PostGroup:
    group_id: str
    post_ids: list[str]
    representative_post_id: str

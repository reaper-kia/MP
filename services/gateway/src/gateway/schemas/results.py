from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from gateway.schemas.common import opt, opt_ts
from gateway.schemas.enums import (
    DATE_STATUS_FROM_PROTO,
    PLATFORM_FROM_PROTO,
    RELEVANCE_FROM_PROTO,
    SENTIMENT_FROM_PROTO,
    TITLE_SOURCE_FROM_PROTO,
    DateStatus,
    Platform,
    Relevance,
    Sentiment,
    TitleSource,
)
from gateway.schemas.searches import SearchCountsOut


class ResultSourceOut(BaseModel):
    id: str | None = Field(description="null — найден глобальным поиском, не в каталоге")
    name: str
    url: str
    is_regional: bool


class ExcerptPartOut(BaseModel):
    text: str
    highlight: bool


class RegionOut(BaseModel):
    by_source: bool
    by_content: bool
    evidence: str | None


class MetricsOut(BaseModel):
    views: int | None
    likes: int | None
    reposts: int | None
    comments: int | None


class ResultOut(BaseModel):
    id: str
    publication_id: str
    platform: Platform
    source: ResultSourceOut
    url: str
    title: str
    title_source: TitleSource
    excerpt: str
    excerpt_parts: list[ExcerptPartOut]
    published_at: datetime | None
    date_status: DateStatus
    relevance: Relevance
    score: float
    explanation: str
    region: RegionOut
    sentiment: Sentiment | None
    group_id: str | None
    group_size: int
    metrics: MetricsOut
    excluded: bool
    found_by_target_id: str

    @classmethod
    def from_proto(cls, r: Any) -> "ResultOut":
        m = r.metrics
        return cls(
            id=r.id,
            publication_id=r.publication_id,
            platform=PLATFORM_FROM_PROTO[r.platform],
            source=ResultSourceOut(
                id=opt(r.source, "source_id"),
                name=r.source.name,
                url=r.source.url,
                is_regional=r.source.is_regional,
            ),
            url=r.url,
            title=r.title,
            title_source=TITLE_SOURCE_FROM_PROTO.get(r.title_source, "post_start"),
            excerpt=r.excerpt,
            excerpt_parts=[
                ExcerptPartOut(text=p.text, highlight=p.highlight) for p in r.excerpt_parts
            ],
            published_at=opt_ts(r, "published_at"),
            date_status=DATE_STATUS_FROM_PROTO.get(r.date_status, "unknown"),
            relevance=RELEVANCE_FROM_PROTO.get(r.relevance, "disputed"),
            score=round(r.score, 4),
            explanation=r.explanation,
            region=RegionOut(
                by_source=r.region.by_source,
                by_content=r.region.by_content,
                evidence=r.region.evidence or None,
            ),
            sentiment=SENTIMENT_FROM_PROTO.get(r.sentiment),
            group_id=opt(r, "group_id"),
            group_size=r.group_size,
            metrics=MetricsOut(
                views=opt(m, "views"),
                likes=opt(m, "likes"),
                reposts=opt(m, "reposts"),
                comments=opt(m, "comments"),
            ),
            excluded=r.excluded,
            found_by_target_id=r.found_by_target_id,
        )


class ResultPageOut(BaseModel):
    items: list[ResultOut]
    total: int
    has_more: bool


class ResultGroupOut(BaseModel):
    group_id: str
    title: str
    size: int
    platforms: list[Platform]
    earliest_published_at: datetime | None
    items: list[ResultOut] = Field(description="Все размещения сюжета")

    @classmethod
    def from_proto(cls, g: Any) -> "ResultGroupOut":
        return cls(
            group_id=g.group_id,
            title=g.title,
            size=g.size,
            platforms=[PLATFORM_FROM_PROTO[p] for p in g.platforms if p in PLATFORM_FROM_PROTO],
            earliest_published_at=opt_ts(g, "earliest_published_at"),
            items=[ResultOut.from_proto(r) for r in g.results],
        )


class GroupPageOut(BaseModel):
    items: list[ResultGroupOut]
    total: int
    has_more: bool


class ExclusionIn(BaseModel):
    result_ids: list[str] = Field(min_length=1)
    excluded: bool


class ExclusionOut(BaseModel):
    counts: SearchCountsOut

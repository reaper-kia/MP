"""Read models — то, что хэндлеры возвращают и transport/grpc/mappers.py кладёт в proto.

Поля один к одному с search.v1 (docs/GRPC.md). None = поле proto не заполняется («нет данных»).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from search_service.domain.enums import (
    DateStatus,
    Platform,
    QueryType,
    Relevance,
    SearchMode,
    SearchStage,
    SearchStatus,
    Sentiment,
    TargetKind,
    TargetStatus,
    TitleSource,
)

# ───────────────────────── источники ─────────────────────────


@dataclass(frozen=True, slots=True)
class SourceView:
    id: UUID
    platform: Platform
    external_id: str
    url: str
    name: str
    city: str | None
    is_regional: bool
    is_active: bool
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SourcePreviewView:
    platform: Platform
    external_id: str
    url: str
    name: str
    city: str | None
    members_count: int | None
    existing_source_id: UUID | None


@dataclass(frozen=True, slots=True)
class SourcePage:
    items: list[SourceView]
    total: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ErrorInfoView:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportRowErrorView:
    row: int
    value: str
    error: ErrorInfoView


@dataclass(frozen=True, slots=True)
class ImportReport:
    created: int
    duplicates: int
    failed: list[ImportRowErrorView] = field(default_factory=list)


# ───────────────────────── поиск ─────────────────────────


@dataclass(frozen=True, slots=True)
class SearchParamsView:
    query: str
    query_type: QueryType | None
    period_from: date
    period_to: date
    mode: SearchMode
    platforms: list[Platform]
    source_ids: list[UUID]


@dataclass(frozen=True, slots=True)
class QueryAnalysisView:
    query_type: QueryType
    summary: str
    search_queries: list[str]
    needs_clarification: bool
    clarification_hint: str


@dataclass(frozen=True, slots=True)
class SearchTargetView:
    id: UUID
    kind: TargetKind
    platform: Platform
    source_id: UUID | None
    name: str
    url: str | None
    status: TargetStatus
    fetched: int
    matched: int
    error: ErrorInfoView | None
    attempts: int
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class SearchCountsView:
    total: int = 0
    direct: int = 0
    indirect: int = 0
    disputed: int = 0
    rejected: int = 0
    excluded: int = 0
    unknown_date: int = 0
    groups: int = 0


@dataclass(frozen=True, slots=True)
class SearchProgressView:
    targets_total: int
    targets_finished: int
    percent: int


@dataclass(frozen=True, slots=True)
class SearchCacheView:
    """Подборка из кэша (B2-20): копия поиска from_search_id, завершённого в created_at."""

    from_search_id: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SearchView:
    id: UUID
    status: SearchStatus
    stage: SearchStage
    progress: SearchProgressView
    params: SearchParamsView
    query_analysis: QueryAnalysisView | None
    targets: list[SearchTargetView]  # в ListSearches — пусто
    counts: SearchCountsView
    warnings: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cache: SearchCacheView | None = None


@dataclass(frozen=True, slots=True)
class SearchPage:
    items: list[SearchView]
    has_more: bool


# ───────────────────────── подборка ─────────────────────────


@dataclass(frozen=True, slots=True)
class ResultSourceView:
    source_id: UUID | None  # None — найден глобально, не в каталоге
    name: str
    url: str
    is_regional: bool


@dataclass(frozen=True, slots=True)
class ExcerptPartView:
    text: str
    highlight: bool


@dataclass(frozen=True, slots=True)
class RegionView:
    by_source: bool
    by_content: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class MetricsView:
    views: int | None = None
    likes: int | None = None
    reposts: int | None = None
    comments: int | None = None


@dataclass(frozen=True, slots=True)
class ResultView:
    id: UUID
    publication_id: UUID
    platform: Platform
    source: ResultSourceView
    url: str
    title: str
    title_source: TitleSource
    excerpt: str
    excerpt_parts: list[ExcerptPartView]
    published_at: datetime | None
    date_status: DateStatus
    relevance: Relevance
    score: float
    explanation: str
    region: RegionView
    sentiment: Sentiment | None
    group_id: str | None
    group_size: int
    metrics: MetricsView
    excluded: bool
    found_by_target_id: UUID


@dataclass(frozen=True, slots=True)
class ResultPage:
    items: list[ResultView]
    total: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ResultGroupView:
    group_id: str
    title: str
    size: int
    platforms: list[Platform]
    earliest_published_at: datetime | None
    results: list[ResultView]  # ВСЕ размещения


@dataclass(frozen=True, slots=True)
class GroupPage:
    items: list[ResultGroupView]
    total: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ExportFile:
    content: bytes
    filename: str
    mime_type: str

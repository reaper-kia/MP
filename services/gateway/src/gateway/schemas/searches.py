from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from gateway.schemas.common import opt, opt_ts, ts
from gateway.schemas.enums import (
    MODE_FROM_PROTO,
    PLATFORM_FROM_PROTO,
    QUERY_TYPE_FROM_PROTO,
    STAGE_FROM_PROTO,
    STATUS_FROM_PROTO,
    TARGET_KIND_FROM_PROTO,
    TARGET_STATUS_FROM_PROTO,
    Platform,
    QueryType,
    SearchMode,
    SearchStage,
    SearchStatus,
    TargetKind,
    TargetStatus,
)
from gateway.schemas.meta import QueryAnalysisOut


class SearchCreateIn(BaseModel):
    query: str = Field(
        min_length=3, max_length=20000, description="Тема, событие, человек или текст новости"
    )
    period_from: date
    period_to: date
    mode: SearchMode
    platforms: list[Platform] = Field(min_length=1)
    source_ids: list[UUID] = Field(
        default_factory=list, description="Обязательно при mode=selected"
    )
    fresh: bool = Field(
        default=False,
        description="true — не брать готовую подборку из кэша, искать заново («Обновить»)",
    )


class RetryIn(BaseModel):
    target_ids: list[str] = Field(default_factory=list, description="Пусто — все failed")


class SearchParamsOut(BaseModel):
    query: str
    query_type: QueryType | None
    period_from: date
    period_to: date
    mode: SearchMode
    platforms: list[Platform]
    source_ids: list[str]

    @classmethod
    def from_proto(cls, p: Any) -> "SearchParamsOut":
        return cls(
            query=p.query,
            query_type=QUERY_TYPE_FROM_PROTO.get(p.query_type),
            period_from=date.fromisoformat(p.period_from),
            period_to=date.fromisoformat(p.period_to),
            mode=MODE_FROM_PROTO.get(p.mode, "selected"),
            platforms=[PLATFORM_FROM_PROTO[x] for x in p.platforms if x in PLATFORM_FROM_PROTO],
            source_ids=list(p.source_ids),
        )


class ErrorInfoOut(BaseModel):
    code: str
    message: str


class SearchTargetOut(BaseModel):
    id: str
    kind: TargetKind
    platform: Platform
    source_id: str | None
    name: str
    url: str | None
    status: TargetStatus
    fetched: int
    matched: int
    error: ErrorInfoOut | None
    attempts: int
    finished_at: datetime | None

    @classmethod
    def from_proto(cls, t: Any) -> "SearchTargetOut":
        return cls(
            id=t.id,
            kind=TARGET_KIND_FROM_PROTO.get(t.kind, "source"),
            platform=PLATFORM_FROM_PROTO[t.platform],
            source_id=opt(t, "source_id"),
            name=t.name,
            url=opt(t, "url"),
            status=TARGET_STATUS_FROM_PROTO.get(t.status, "pending"),
            fetched=t.fetched,
            matched=t.matched,
            error=(
                ErrorInfoOut(code=t.error.code, message=t.error.message)
                if t.HasField("error")
                else None
            ),
            attempts=t.attempts,
            finished_at=opt_ts(t, "finished_at"),
        )


class SearchCountsOut(BaseModel):
    total: int
    direct: int
    indirect: int
    disputed: int
    rejected: int
    excluded: int
    unknown_date: int
    groups: int

    @classmethod
    def from_proto(cls, c: Any) -> "SearchCountsOut":
        return cls(
            total=c.total,
            direct=c.direct,
            indirect=c.indirect,
            disputed=c.disputed,
            rejected=c.rejected,
            excluded=c.excluded,
            unknown_date=c.unknown_date,
            groups=c.groups,
        )


class SearchProgressOut(BaseModel):
    targets_total: int
    targets_finished: int
    percent: int


class SearchCacheOut(BaseModel):
    """Подборка из кэша: копия поиска from_search_id, собранного в created_at."""

    from_search_id: UUID
    created_at: datetime

    @classmethod
    def from_proto(cls, s: Any) -> "SearchCacheOut | None":
        if not s.HasField("cache"):
            return None
        return cls(from_search_id=UUID(s.cache.from_search_id), created_at=ts(s.cache.created_at))


class SearchOut(BaseModel):
    id: UUID
    status: SearchStatus
    stage: SearchStage
    progress: SearchProgressOut
    params: SearchParamsOut
    query_analysis: QueryAnalysisOut | None
    targets: list[SearchTargetOut]
    counts: SearchCountsOut
    warnings: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cache: SearchCacheOut | None = Field(
        description="Не null — подборка взята из кэша: копия недавнего такого же поиска"
    )

    @classmethod
    def from_proto(cls, s: Any) -> "SearchOut":
        return cls(
            id=UUID(s.id),
            status=STATUS_FROM_PROTO.get(s.status, "queued"),
            stage=STAGE_FROM_PROTO.get(s.stage, "queued"),
            progress=SearchProgressOut(
                targets_total=s.progress.targets_total,
                targets_finished=s.progress.targets_finished,
                percent=s.progress.percent,
            ),
            params=SearchParamsOut.from_proto(s.params),
            query_analysis=(
                QueryAnalysisOut.from_proto(s.query_analysis, QUERY_TYPE_FROM_PROTO)
                if s.HasField("query_analysis")
                else None
            ),
            targets=[SearchTargetOut.from_proto(t) for t in s.targets],
            counts=SearchCountsOut.from_proto(s.counts),
            warnings=list(s.warnings),
            created_at=ts(s.created_at),
            started_at=opt_ts(s, "started_at"),
            finished_at=opt_ts(s, "finished_at"),
            cache=SearchCacheOut.from_proto(s),
        )


class SearchSummaryOut(BaseModel):
    id: UUID
    status: SearchStatus
    params: SearchParamsOut
    counts: SearchCountsOut
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def from_proto(cls, s: Any) -> "SearchSummaryOut":
        return cls(
            id=UUID(s.id),
            status=STATUS_FROM_PROTO.get(s.status, "queued"),
            params=SearchParamsOut.from_proto(s.params),
            counts=SearchCountsOut.from_proto(s.counts),
            created_at=ts(s.created_at),
            finished_at=opt_ts(s, "finished_at"),
        )


class SearchSummaryPageOut(BaseModel):
    items: list[SearchSummaryOut]
    has_more: bool

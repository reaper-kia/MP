"""proto ⇄ команды / read models. Логики нет — только перевод типов (поля — docs/GRPC.md)."""

from collections.abc import Callable, Iterable
from datetime import date, datetime
from uuid import UUID

from common.v1 import common_pb2, platform_pb2
from google.protobuf.timestamp_pb2 import Timestamp
from search.v1 import search_service_pb2 as pb

from search_service.applications.context import RequestContext
from search_service.applications.exceptions import SearchInvalidParamsError
from search_service.applications.queries.results import ResultFilter
from search_service.applications.results.read_models import (
    ErrorInfoView,
    ImportReport,
    QueryAnalysisView,
    ResultGroupView,
    ResultView,
    SearchCountsView,
    SearchParamsView,
    SearchTargetView,
    SearchView,
    SourcePreviewView,
    SourceView,
)
from search_service.domain.enums import (
    DateStatus,
    ExportFormat,
    Platform,
    QueryType,
    Relevance,
    ResultSort,
    SearchMode,
    SearchStage,
    SearchStatus,
    Sentiment,
    TargetKind,
    TargetStatus,
    TitleSource,
)

# ───────────────────────── enum'ы ─────────────────────────

PLATFORM_TO_PROTO: dict[Platform, platform_pb2.Platform] = {
    Platform.VK: platform_pb2.PLATFORM_VK,
    Platform.OK: platform_pb2.PLATFORM_OK,
    Platform.MAX: platform_pb2.PLATFORM_MAX,
    Platform.NEWS: platform_pb2.PLATFORM_NEWS,
}
MODE_TO_PROTO: dict[SearchMode, pb.SearchMode] = {
    SearchMode.SELECTED: pb.SEARCH_MODE_SELECTED,
    SearchMode.GLOBAL: pb.SEARCH_MODE_GLOBAL,
}
STATUS_TO_PROTO: dict[SearchStatus, pb.SearchStatus] = {
    SearchStatus.QUEUED: pb.SEARCH_STATUS_QUEUED,
    SearchStatus.RUNNING: pb.SEARCH_STATUS_RUNNING,
    SearchStatus.COMPLETED: pb.SEARCH_STATUS_COMPLETED,
    SearchStatus.PARTIAL: pb.SEARCH_STATUS_PARTIAL,
    SearchStatus.FAILED: pb.SEARCH_STATUS_FAILED,
    SearchStatus.CANCELLED: pb.SEARCH_STATUS_CANCELLED,
}
STAGE_TO_PROTO: dict[SearchStage, pb.SearchStage] = {
    SearchStage.QUEUED: pb.SEARCH_STAGE_QUEUED,
    SearchStage.ANALYZING_QUERY: pb.SEARCH_STAGE_ANALYZING_QUERY,
    SearchStage.COLLECTING: pb.SEARCH_STAGE_COLLECTING,
    SearchStage.SCORING: pb.SEARCH_STAGE_SCORING,
    SearchStage.GROUPING: pb.SEARCH_STAGE_GROUPING,
    SearchStage.DONE: pb.SEARCH_STAGE_DONE,
}
QUERY_TYPE_TO_PROTO: dict[QueryType, pb.QueryType] = {
    QueryType.TOPIC: pb.QUERY_TYPE_TOPIC,
    QueryType.EVENT: pb.QUERY_TYPE_EVENT,
    QueryType.PERSON: pb.QUERY_TYPE_PERSON,
    QueryType.NEWS_TEXT: pb.QUERY_TYPE_NEWS_TEXT,
}
TARGET_KIND_TO_PROTO: dict[TargetKind, pb.TargetKind] = {
    TargetKind.SOURCE: pb.TARGET_KIND_SOURCE,
    TargetKind.PLATFORM_SEARCH: pb.TARGET_KIND_PLATFORM_SEARCH,
}
TARGET_STATUS_TO_PROTO: dict[TargetStatus, pb.TargetStatus] = {
    TargetStatus.PENDING: pb.TARGET_STATUS_PENDING,
    TargetStatus.RUNNING: pb.TARGET_STATUS_RUNNING,
    TargetStatus.DONE: pb.TARGET_STATUS_DONE,
    TargetStatus.EMPTY: pb.TARGET_STATUS_EMPTY,
    TargetStatus.FAILED: pb.TARGET_STATUS_FAILED,
    TargetStatus.SKIPPED: pb.TARGET_STATUS_SKIPPED,
}
RELEVANCE_TO_PROTO: dict[Relevance, pb.Relevance] = {
    Relevance.DIRECT: pb.RELEVANCE_DIRECT,
    Relevance.INDIRECT: pb.RELEVANCE_INDIRECT,
    Relevance.DISPUTED: pb.RELEVANCE_DISPUTED,
    Relevance.IRRELEVANT: pb.RELEVANCE_IRRELEVANT,
}
SENTIMENT_TO_PROTO: dict[Sentiment, pb.Sentiment] = {
    Sentiment.POSITIVE: pb.SENTIMENT_POSITIVE,
    Sentiment.NEUTRAL: pb.SENTIMENT_NEUTRAL,
    Sentiment.NEGATIVE: pb.SENTIMENT_NEGATIVE,
}
TITLE_SOURCE_TO_PROTO: dict[TitleSource, pb.TitleSource] = {
    TitleSource.TITLE: pb.TITLE_SOURCE_TITLE,
    TitleSource.POST_START: pb.TITLE_SOURCE_POST_START,
}
DATE_STATUS_TO_PROTO: dict[DateStatus, pb.DateStatus] = {
    DateStatus.IN_PERIOD: pb.DATE_STATUS_IN_PERIOD,
    DateStatus.UNKNOWN: pb.DATE_STATUS_UNKNOWN,
}
SORT_FROM_PROTO: dict[int, ResultSort] = {
    pb.RESULT_SORT_RELEVANCE: ResultSort.RELEVANCE,
    pb.RESULT_SORT_DATE_DESC: ResultSort.DATE_DESC,
    pb.RESULT_SORT_DATE_ASC: ResultSort.DATE_ASC,
}
FORMAT_FROM_PROTO: dict[int, ExportFormat] = {
    pb.EXPORT_FORMAT_XLSX: ExportFormat.XLSX,
    pb.EXPORT_FORMAT_DOCX: ExportFormat.DOCX,
}


PLATFORM_FROM_PROTO: dict[int, Platform] = {v: k for k, v in PLATFORM_TO_PROTO.items()}
MODE_FROM_PROTO: dict[int, SearchMode] = {v: k for k, v in MODE_TO_PROTO.items()}
RELEVANCE_FROM_PROTO: dict[int, Relevance] = {v: k for k, v in RELEVANCE_TO_PROTO.items()}
DATE_STATUS_FROM_PROTO: dict[int, DateStatus] = {v: k for k, v in DATE_STATUS_TO_PROTO.items()}


# ───────────────────────── входные данные ─────────────────────────


def context_from_proto(ctx: common_pb2.RequestContext) -> RequestContext:
    return RequestContext(request_id=ctx.request_id, actor=ctx.actor_user_id)


def parse_uuid(value: str, error: Callable[[str], Exception]) -> UUID:
    """Кривой id = «не найдено» (как в шаблоне): наружу не сообщаем, что формат неверный."""
    try:
        return UUID(value)
    except ValueError as e:
        raise error("Не найдено") from e


def parse_uuids(values: Iterable[str], field: str) -> list[UUID]:
    try:
        return [UUID(v) for v in values]
    except ValueError as e:
        raise SearchInvalidParamsError(f"{field}: неверный идентификатор") from e


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise SearchInvalidParamsError(f"{field}: ожидается дата YYYY-MM-DD") from e


def platforms_from_proto(values: Iterable[int], field: str = "platforms") -> list[Platform]:
    result = []
    for value in values:
        platform = PLATFORM_FROM_PROTO.get(value)
        if platform is None:
            raise SearchInvalidParamsError(f"{field}: неизвестная площадка")
        result.append(platform)
    return result


def mode_from_proto(value: int) -> SearchMode:
    mode = MODE_FROM_PROTO.get(value)
    if mode is None:
        raise SearchInvalidParamsError("mode: укажите selected или global")
    return mode


def filter_from_proto(f: pb.ResultFilter) -> ResultFilter:
    return ResultFilter(
        relevance=[RELEVANCE_FROM_PROTO[r] for r in f.relevance if r in RELEVANCE_FROM_PROTO],
        platforms=platforms_from_proto(f.platforms, "platform"),
        target_ids=parse_uuids(f.target_ids, "target_id"),
        date_status=[
            DATE_STATUS_FROM_PROTO[d] for d in f.date_status if d in DATE_STATUS_FROM_PROTO
        ],
        include_excluded=f.include_excluded,
    )


def sort_from_proto(value: int) -> ResultSort:
    return SORT_FROM_PROTO.get(value, ResultSort.RELEVANCE)


def format_from_proto(value: int) -> ExportFormat:
    return FORMAT_FROM_PROTO.get(value, ExportFormat.XLSX)


# ───────────────────────── выходные данные ─────────────────────────


def to_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def error_info_to_proto(e: ErrorInfoView) -> platform_pb2.ErrorInfo:
    return platform_pb2.ErrorInfo(code=e.code, message=e.message)


def source_to_proto(s: SourceView) -> pb.Source:
    message = pb.Source(
        id=str(s.id),
        platform=PLATFORM_TO_PROTO[s.platform],
        external_id=s.external_id,
        url=s.url,
        name=s.name,
        is_regional=s.is_regional,
        is_active=s.is_active,
        notes=s.notes,
        created_at=to_timestamp(s.created_at),
        updated_at=to_timestamp(s.updated_at),
    )
    if s.city is not None:
        message.city = s.city
    return message


def preview_to_proto(p: SourcePreviewView) -> pb.SourcePreview:
    message = pb.SourcePreview(
        platform=PLATFORM_TO_PROTO[p.platform], external_id=p.external_id, url=p.url, name=p.name
    )
    if p.city is not None:
        message.city = p.city
    if p.members_count is not None:
        message.members_count = p.members_count
    if p.existing_source_id is not None:
        message.existing_source_id = str(p.existing_source_id)
    return message


def import_report_to_proto(r: ImportReport) -> pb.ImportSourcesResponse:
    return pb.ImportSourcesResponse(
        created=r.created,
        duplicates=r.duplicates,
        failed=[
            pb.ImportRowError(row=f.row, value=f.value, error=error_info_to_proto(f.error))
            for f in r.failed
        ],
    )


def params_to_proto(p: SearchParamsView) -> pb.SearchParams:
    return pb.SearchParams(
        query=p.query,
        query_type=(
            QUERY_TYPE_TO_PROTO[p.query_type]
            if p.query_type is not None
            else pb.QUERY_TYPE_UNSPECIFIED
        ),
        period_from=p.period_from.isoformat(),
        period_to=p.period_to.isoformat(),
        mode=MODE_TO_PROTO[p.mode],
        platforms=[PLATFORM_TO_PROTO[x] for x in p.platforms],
        source_ids=[str(x) for x in p.source_ids],
    )


def analysis_to_proto(a: QueryAnalysisView) -> pb.QueryAnalysisView:
    return pb.QueryAnalysisView(
        query_type=QUERY_TYPE_TO_PROTO[a.query_type],
        summary=a.summary,
        search_queries=list(a.search_queries),
        needs_clarification=a.needs_clarification,
        clarification_hint=a.clarification_hint,
    )


def counts_to_proto(c: SearchCountsView) -> pb.SearchCounts:
    return pb.SearchCounts(
        total=c.total,
        direct=c.direct,
        indirect=c.indirect,
        disputed=c.disputed,
        rejected=c.rejected,
        excluded=c.excluded,
        unknown_date=c.unknown_date,
        groups=c.groups,
    )


def target_to_proto(t: SearchTargetView) -> pb.SearchTarget:
    message = pb.SearchTarget(
        id=str(t.id),
        kind=TARGET_KIND_TO_PROTO[t.kind],
        platform=PLATFORM_TO_PROTO[t.platform],
        name=t.name,
        status=TARGET_STATUS_TO_PROTO[t.status],
        fetched=t.fetched,
        matched=t.matched,
        attempts=t.attempts,
    )
    if t.source_id is not None:
        message.source_id = str(t.source_id)
    if t.url is not None:
        message.url = t.url
    if t.error is not None:
        message.error.CopyFrom(error_info_to_proto(t.error))
    if t.finished_at is not None:
        message.finished_at.CopyFrom(to_timestamp(t.finished_at))
    return message


def search_to_proto(s: SearchView) -> pb.Search:
    message = pb.Search(
        id=str(s.id),
        status=STATUS_TO_PROTO[s.status],
        stage=STAGE_TO_PROTO[s.stage],
        progress=pb.SearchProgress(
            targets_total=s.progress.targets_total,
            targets_finished=s.progress.targets_finished,
            percent=s.progress.percent,
        ),
        params=params_to_proto(s.params),
        targets=[target_to_proto(t) for t in s.targets],
        counts=counts_to_proto(s.counts),
        warnings=list(s.warnings),
        created_at=to_timestamp(s.created_at),
    )
    if s.query_analysis is not None:
        message.query_analysis.CopyFrom(analysis_to_proto(s.query_analysis))
    if s.started_at is not None:
        message.started_at.CopyFrom(to_timestamp(s.started_at))
    if s.finished_at is not None:
        message.finished_at.CopyFrom(to_timestamp(s.finished_at))
    if s.cache is not None:
        message.cache.CopyFrom(
            pb.SearchCacheInfo(
                from_search_id=str(s.cache.from_search_id),
                created_at=to_timestamp(s.cache.created_at),
            )
        )
    return message


def result_to_proto(r: ResultView) -> pb.Result:
    source = pb.ResultSourceRef(
        name=r.source.name, url=r.source.url, is_regional=r.source.is_regional
    )
    if r.source.source_id is not None:
        source.source_id = str(r.source.source_id)
    message = pb.Result(
        id=str(r.id),
        publication_id=str(r.publication_id),
        platform=PLATFORM_TO_PROTO[r.platform],
        source=source,
        url=r.url,
        title=r.title,
        title_source=TITLE_SOURCE_TO_PROTO[r.title_source],
        excerpt=r.excerpt,
        excerpt_parts=[pb.ExcerptPart(text=p.text, highlight=p.highlight) for p in r.excerpt_parts],
        date_status=DATE_STATUS_TO_PROTO[r.date_status],
        relevance=RELEVANCE_TO_PROTO[r.relevance],
        score=r.score,
        explanation=r.explanation,
        region=pb.ResultRegion(
            by_source=r.region.by_source, by_content=r.region.by_content, evidence=r.region.evidence
        ),
        sentiment=(
            SENTIMENT_TO_PROTO[r.sentiment] if r.sentiment is not None else pb.SENTIMENT_UNSPECIFIED
        ),
        group_size=r.group_size,
        excluded=r.excluded,
        found_by_target_id=str(r.found_by_target_id),
    )
    if r.published_at is not None:
        message.published_at.CopyFrom(to_timestamp(r.published_at))
    if r.group_id is not None:
        message.group_id = r.group_id
    m = r.metrics
    if m.views is not None:
        message.metrics.views = m.views
    if m.likes is not None:
        message.metrics.likes = m.likes
    if m.reposts is not None:
        message.metrics.reposts = m.reposts
    if m.comments is not None:
        message.metrics.comments = m.comments
    return message


def group_to_proto(g: ResultGroupView) -> pb.ResultGroup:
    message = pb.ResultGroup(
        group_id=g.group_id,
        title=g.title,
        size=g.size,
        platforms=[PLATFORM_TO_PROTO[p] for p in g.platforms],
        results=[result_to_proto(r) for r in g.results],
    )
    if g.earliest_published_at is not None:
        message.earliest_published_at.CopyFrom(to_timestamp(g.earliest_published_at))
    return message

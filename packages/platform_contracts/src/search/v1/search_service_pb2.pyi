import datetime

from common.v1 import common_pb2 as _common_pb2
from common.v1 import platform_pb2 as _platform_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SearchMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEARCH_MODE_UNSPECIFIED: _ClassVar[SearchMode]
    SEARCH_MODE_SELECTED: _ClassVar[SearchMode]
    SEARCH_MODE_GLOBAL: _ClassVar[SearchMode]

class SearchStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEARCH_STATUS_UNSPECIFIED: _ClassVar[SearchStatus]
    SEARCH_STATUS_QUEUED: _ClassVar[SearchStatus]
    SEARCH_STATUS_RUNNING: _ClassVar[SearchStatus]
    SEARCH_STATUS_COMPLETED: _ClassVar[SearchStatus]
    SEARCH_STATUS_PARTIAL: _ClassVar[SearchStatus]
    SEARCH_STATUS_FAILED: _ClassVar[SearchStatus]
    SEARCH_STATUS_CANCELLED: _ClassVar[SearchStatus]

class SearchStage(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEARCH_STAGE_UNSPECIFIED: _ClassVar[SearchStage]
    SEARCH_STAGE_QUEUED: _ClassVar[SearchStage]
    SEARCH_STAGE_ANALYZING_QUERY: _ClassVar[SearchStage]
    SEARCH_STAGE_COLLECTING: _ClassVar[SearchStage]
    SEARCH_STAGE_SCORING: _ClassVar[SearchStage]
    SEARCH_STAGE_GROUPING: _ClassVar[SearchStage]
    SEARCH_STAGE_DONE: _ClassVar[SearchStage]

class QueryType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    QUERY_TYPE_UNSPECIFIED: _ClassVar[QueryType]
    QUERY_TYPE_TOPIC: _ClassVar[QueryType]
    QUERY_TYPE_EVENT: _ClassVar[QueryType]
    QUERY_TYPE_PERSON: _ClassVar[QueryType]
    QUERY_TYPE_NEWS_TEXT: _ClassVar[QueryType]

class TargetKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TARGET_KIND_UNSPECIFIED: _ClassVar[TargetKind]
    TARGET_KIND_SOURCE: _ClassVar[TargetKind]
    TARGET_KIND_PLATFORM_SEARCH: _ClassVar[TargetKind]

class TargetStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TARGET_STATUS_UNSPECIFIED: _ClassVar[TargetStatus]
    TARGET_STATUS_PENDING: _ClassVar[TargetStatus]
    TARGET_STATUS_RUNNING: _ClassVar[TargetStatus]
    TARGET_STATUS_DONE: _ClassVar[TargetStatus]
    TARGET_STATUS_EMPTY: _ClassVar[TargetStatus]
    TARGET_STATUS_FAILED: _ClassVar[TargetStatus]
    TARGET_STATUS_SKIPPED: _ClassVar[TargetStatus]

class Relevance(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RELEVANCE_UNSPECIFIED: _ClassVar[Relevance]
    RELEVANCE_DIRECT: _ClassVar[Relevance]
    RELEVANCE_INDIRECT: _ClassVar[Relevance]
    RELEVANCE_DISPUTED: _ClassVar[Relevance]
    RELEVANCE_IRRELEVANT: _ClassVar[Relevance]

class Sentiment(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SENTIMENT_UNSPECIFIED: _ClassVar[Sentiment]
    SENTIMENT_POSITIVE: _ClassVar[Sentiment]
    SENTIMENT_NEUTRAL: _ClassVar[Sentiment]
    SENTIMENT_NEGATIVE: _ClassVar[Sentiment]

class TitleSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TITLE_SOURCE_UNSPECIFIED: _ClassVar[TitleSource]
    TITLE_SOURCE_TITLE: _ClassVar[TitleSource]
    TITLE_SOURCE_POST_START: _ClassVar[TitleSource]

class DateStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DATE_STATUS_UNSPECIFIED: _ClassVar[DateStatus]
    DATE_STATUS_IN_PERIOD: _ClassVar[DateStatus]
    DATE_STATUS_UNKNOWN: _ClassVar[DateStatus]

class ResultSort(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESULT_SORT_UNSPECIFIED: _ClassVar[ResultSort]
    RESULT_SORT_RELEVANCE: _ClassVar[ResultSort]
    RESULT_SORT_DATE_DESC: _ClassVar[ResultSort]
    RESULT_SORT_DATE_ASC: _ClassVar[ResultSort]

class ExportFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXPORT_FORMAT_UNSPECIFIED: _ClassVar[ExportFormat]
    EXPORT_FORMAT_XLSX: _ClassVar[ExportFormat]
    EXPORT_FORMAT_DOCX: _ClassVar[ExportFormat]
SEARCH_MODE_UNSPECIFIED: SearchMode
SEARCH_MODE_SELECTED: SearchMode
SEARCH_MODE_GLOBAL: SearchMode
SEARCH_STATUS_UNSPECIFIED: SearchStatus
SEARCH_STATUS_QUEUED: SearchStatus
SEARCH_STATUS_RUNNING: SearchStatus
SEARCH_STATUS_COMPLETED: SearchStatus
SEARCH_STATUS_PARTIAL: SearchStatus
SEARCH_STATUS_FAILED: SearchStatus
SEARCH_STATUS_CANCELLED: SearchStatus
SEARCH_STAGE_UNSPECIFIED: SearchStage
SEARCH_STAGE_QUEUED: SearchStage
SEARCH_STAGE_ANALYZING_QUERY: SearchStage
SEARCH_STAGE_COLLECTING: SearchStage
SEARCH_STAGE_SCORING: SearchStage
SEARCH_STAGE_GROUPING: SearchStage
SEARCH_STAGE_DONE: SearchStage
QUERY_TYPE_UNSPECIFIED: QueryType
QUERY_TYPE_TOPIC: QueryType
QUERY_TYPE_EVENT: QueryType
QUERY_TYPE_PERSON: QueryType
QUERY_TYPE_NEWS_TEXT: QueryType
TARGET_KIND_UNSPECIFIED: TargetKind
TARGET_KIND_SOURCE: TargetKind
TARGET_KIND_PLATFORM_SEARCH: TargetKind
TARGET_STATUS_UNSPECIFIED: TargetStatus
TARGET_STATUS_PENDING: TargetStatus
TARGET_STATUS_RUNNING: TargetStatus
TARGET_STATUS_DONE: TargetStatus
TARGET_STATUS_EMPTY: TargetStatus
TARGET_STATUS_FAILED: TargetStatus
TARGET_STATUS_SKIPPED: TargetStatus
RELEVANCE_UNSPECIFIED: Relevance
RELEVANCE_DIRECT: Relevance
RELEVANCE_INDIRECT: Relevance
RELEVANCE_DISPUTED: Relevance
RELEVANCE_IRRELEVANT: Relevance
SENTIMENT_UNSPECIFIED: Sentiment
SENTIMENT_POSITIVE: Sentiment
SENTIMENT_NEUTRAL: Sentiment
SENTIMENT_NEGATIVE: Sentiment
TITLE_SOURCE_UNSPECIFIED: TitleSource
TITLE_SOURCE_TITLE: TitleSource
TITLE_SOURCE_POST_START: TitleSource
DATE_STATUS_UNSPECIFIED: DateStatus
DATE_STATUS_IN_PERIOD: DateStatus
DATE_STATUS_UNKNOWN: DateStatus
RESULT_SORT_UNSPECIFIED: ResultSort
RESULT_SORT_RELEVANCE: ResultSort
RESULT_SORT_DATE_DESC: ResultSort
RESULT_SORT_DATE_ASC: ResultSort
EXPORT_FORMAT_UNSPECIFIED: ExportFormat
EXPORT_FORMAT_XLSX: ExportFormat
EXPORT_FORMAT_DOCX: ExportFormat

class Source(_message.Message):
    __slots__ = ("id", "platform", "external_id", "url", "name", "city", "is_regional", "is_active", "notes", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    IS_REGIONAL_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    platform: _platform_pb2.Platform
    external_id: str
    url: str
    name: str
    city: str
    is_regional: bool
    is_active: bool
    notes: str
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., external_id: _Optional[str] = ..., url: _Optional[str] = ..., name: _Optional[str] = ..., city: _Optional[str] = ..., is_regional: _Optional[bool] = ..., is_active: _Optional[bool] = ..., notes: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SourcePreview(_message.Message):
    __slots__ = ("platform", "external_id", "url", "name", "city", "members_count", "existing_source_id")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_COUNT_FIELD_NUMBER: _ClassVar[int]
    EXISTING_SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    platform: _platform_pb2.Platform
    external_id: str
    url: str
    name: str
    city: str
    members_count: int
    existing_source_id: str
    def __init__(self, platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., external_id: _Optional[str] = ..., url: _Optional[str] = ..., name: _Optional[str] = ..., city: _Optional[str] = ..., members_count: _Optional[int] = ..., existing_source_id: _Optional[str] = ...) -> None: ...

class ResolveSourceRequest(_message.Message):
    __slots__ = ("context", "url")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    url: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., url: _Optional[str] = ...) -> None: ...

class ResolveSourceResponse(_message.Message):
    __slots__ = ("preview",)
    PREVIEW_FIELD_NUMBER: _ClassVar[int]
    preview: SourcePreview
    def __init__(self, preview: _Optional[_Union[SourcePreview, _Mapping]] = ...) -> None: ...

class CreateSourceRequest(_message.Message):
    __slots__ = ("context", "url", "name", "is_regional", "notes")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    IS_REGIONAL_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    url: str
    name: str
    is_regional: bool
    notes: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., url: _Optional[str] = ..., name: _Optional[str] = ..., is_regional: _Optional[bool] = ..., notes: _Optional[str] = ...) -> None: ...

class CreateSourceResponse(_message.Message):
    __slots__ = ("source",)
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    source: Source
    def __init__(self, source: _Optional[_Union[Source, _Mapping]] = ...) -> None: ...

class ListSourcesRequest(_message.Message):
    __slots__ = ("context", "platforms", "q", "is_active", "limit", "offset")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    Q_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    platforms: _containers.RepeatedScalarFieldContainer[_platform_pb2.Platform]
    q: str
    is_active: bool
    limit: int
    offset: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., platforms: _Optional[_Iterable[_Union[_platform_pb2.Platform, str]]] = ..., q: _Optional[str] = ..., is_active: _Optional[bool] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListSourcesResponse(_message.Message):
    __slots__ = ("sources", "total", "has_more")
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    sources: _containers.RepeatedCompositeFieldContainer[Source]
    total: int
    has_more: bool
    def __init__(self, sources: _Optional[_Iterable[_Union[Source, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: _Optional[bool] = ...) -> None: ...

class UpdateSourceRequest(_message.Message):
    __slots__ = ("context", "source_id", "name", "is_regional", "is_active", "notes")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    IS_REGIONAL_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    source_id: str
    name: str
    is_regional: bool
    is_active: bool
    notes: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., source_id: _Optional[str] = ..., name: _Optional[str] = ..., is_regional: _Optional[bool] = ..., is_active: _Optional[bool] = ..., notes: _Optional[str] = ...) -> None: ...

class UpdateSourceResponse(_message.Message):
    __slots__ = ("source",)
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    source: Source
    def __init__(self, source: _Optional[_Union[Source, _Mapping]] = ...) -> None: ...

class DeleteSourceRequest(_message.Message):
    __slots__ = ("context", "source_id")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    source_id: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., source_id: _Optional[str] = ...) -> None: ...

class DeleteSourceResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ImportSourcesRequest(_message.Message):
    __slots__ = ("context", "xlsx")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    XLSX_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    xlsx: bytes
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., xlsx: _Optional[bytes] = ...) -> None: ...

class ImportRowError(_message.Message):
    __slots__ = ("row", "value", "error")
    ROW_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    row: int
    value: str
    error: _platform_pb2.ErrorInfo
    def __init__(self, row: _Optional[int] = ..., value: _Optional[str] = ..., error: _Optional[_Union[_platform_pb2.ErrorInfo, _Mapping]] = ...) -> None: ...

class ImportSourcesResponse(_message.Message):
    __slots__ = ("created", "duplicates", "failed")
    CREATED_FIELD_NUMBER: _ClassVar[int]
    DUPLICATES_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    created: int
    duplicates: int
    failed: _containers.RepeatedCompositeFieldContainer[ImportRowError]
    def __init__(self, created: _Optional[int] = ..., duplicates: _Optional[int] = ..., failed: _Optional[_Iterable[_Union[ImportRowError, _Mapping]]] = ...) -> None: ...

class SearchParams(_message.Message):
    __slots__ = ("query", "query_type", "period_from", "period_to", "mode", "platforms", "source_ids")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    QUERY_TYPE_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_IDS_FIELD_NUMBER: _ClassVar[int]
    query: str
    query_type: QueryType
    period_from: str
    period_to: str
    mode: SearchMode
    platforms: _containers.RepeatedScalarFieldContainer[_platform_pb2.Platform]
    source_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, query: _Optional[str] = ..., query_type: _Optional[_Union[QueryType, str]] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ..., mode: _Optional[_Union[SearchMode, str]] = ..., platforms: _Optional[_Iterable[_Union[_platform_pb2.Platform, str]]] = ..., source_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class SearchTarget(_message.Message):
    __slots__ = ("id", "kind", "platform", "source_id", "name", "url", "status", "fetched", "matched", "error", "attempts", "finished_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    FETCHED_FIELD_NUMBER: _ClassVar[int]
    MATCHED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    kind: TargetKind
    platform: _platform_pb2.Platform
    source_id: str
    name: str
    url: str
    status: TargetStatus
    fetched: int
    matched: int
    error: _platform_pb2.ErrorInfo
    attempts: int
    finished_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., kind: _Optional[_Union[TargetKind, str]] = ..., platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., source_id: _Optional[str] = ..., name: _Optional[str] = ..., url: _Optional[str] = ..., status: _Optional[_Union[TargetStatus, str]] = ..., fetched: _Optional[int] = ..., matched: _Optional[int] = ..., error: _Optional[_Union[_platform_pb2.ErrorInfo, _Mapping]] = ..., attempts: _Optional[int] = ..., finished_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SearchCounts(_message.Message):
    __slots__ = ("total", "direct", "indirect", "disputed", "rejected", "excluded", "unknown_date", "groups")
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    DIRECT_FIELD_NUMBER: _ClassVar[int]
    INDIRECT_FIELD_NUMBER: _ClassVar[int]
    DISPUTED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    EXCLUDED_FIELD_NUMBER: _ClassVar[int]
    UNKNOWN_DATE_FIELD_NUMBER: _ClassVar[int]
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    total: int
    direct: int
    indirect: int
    disputed: int
    rejected: int
    excluded: int
    unknown_date: int
    groups: int
    def __init__(self, total: _Optional[int] = ..., direct: _Optional[int] = ..., indirect: _Optional[int] = ..., disputed: _Optional[int] = ..., rejected: _Optional[int] = ..., excluded: _Optional[int] = ..., unknown_date: _Optional[int] = ..., groups: _Optional[int] = ...) -> None: ...

class SearchProgress(_message.Message):
    __slots__ = ("targets_total", "targets_finished", "percent")
    TARGETS_TOTAL_FIELD_NUMBER: _ClassVar[int]
    TARGETS_FINISHED_FIELD_NUMBER: _ClassVar[int]
    PERCENT_FIELD_NUMBER: _ClassVar[int]
    targets_total: int
    targets_finished: int
    percent: int
    def __init__(self, targets_total: _Optional[int] = ..., targets_finished: _Optional[int] = ..., percent: _Optional[int] = ...) -> None: ...

class QueryAnalysisView(_message.Message):
    __slots__ = ("query_type", "summary", "search_queries", "needs_clarification", "clarification_hint")
    QUERY_TYPE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    SEARCH_QUERIES_FIELD_NUMBER: _ClassVar[int]
    NEEDS_CLARIFICATION_FIELD_NUMBER: _ClassVar[int]
    CLARIFICATION_HINT_FIELD_NUMBER: _ClassVar[int]
    query_type: QueryType
    summary: str
    search_queries: _containers.RepeatedScalarFieldContainer[str]
    needs_clarification: bool
    clarification_hint: str
    def __init__(self, query_type: _Optional[_Union[QueryType, str]] = ..., summary: _Optional[str] = ..., search_queries: _Optional[_Iterable[str]] = ..., needs_clarification: _Optional[bool] = ..., clarification_hint: _Optional[str] = ...) -> None: ...

class Search(_message.Message):
    __slots__ = ("id", "status", "stage", "progress", "params", "query_analysis", "targets", "counts", "warnings", "created_at", "started_at", "finished_at", "cache")
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STAGE_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    QUERY_ANALYSIS_FIELD_NUMBER: _ClassVar[int]
    TARGETS_FIELD_NUMBER: _ClassVar[int]
    COUNTS_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    CACHE_FIELD_NUMBER: _ClassVar[int]
    id: str
    status: SearchStatus
    stage: SearchStage
    progress: SearchProgress
    params: SearchParams
    query_analysis: QueryAnalysisView
    targets: _containers.RepeatedCompositeFieldContainer[SearchTarget]
    counts: SearchCounts
    warnings: _containers.RepeatedScalarFieldContainer[str]
    created_at: _timestamp_pb2.Timestamp
    started_at: _timestamp_pb2.Timestamp
    finished_at: _timestamp_pb2.Timestamp
    cache: SearchCacheInfo
    def __init__(self, id: _Optional[str] = ..., status: _Optional[_Union[SearchStatus, str]] = ..., stage: _Optional[_Union[SearchStage, str]] = ..., progress: _Optional[_Union[SearchProgress, _Mapping]] = ..., params: _Optional[_Union[SearchParams, _Mapping]] = ..., query_analysis: _Optional[_Union[QueryAnalysisView, _Mapping]] = ..., targets: _Optional[_Iterable[_Union[SearchTarget, _Mapping]]] = ..., counts: _Optional[_Union[SearchCounts, _Mapping]] = ..., warnings: _Optional[_Iterable[str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., finished_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., cache: _Optional[_Union[SearchCacheInfo, _Mapping]] = ...) -> None: ...

class SearchCacheInfo(_message.Message):
    __slots__ = ("from_search_id", "created_at")
    FROM_SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    from_search_id: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, from_search_id: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class StartSearchRequest(_message.Message):
    __slots__ = ("context", "query", "period_from", "period_to", "mode", "platforms", "source_ids", "fresh")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_IDS_FIELD_NUMBER: _ClassVar[int]
    FRESH_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    query: str
    period_from: str
    period_to: str
    mode: SearchMode
    platforms: _containers.RepeatedScalarFieldContainer[_platform_pb2.Platform]
    source_ids: _containers.RepeatedScalarFieldContainer[str]
    fresh: bool
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., query: _Optional[str] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ..., mode: _Optional[_Union[SearchMode, str]] = ..., platforms: _Optional[_Iterable[_Union[_platform_pb2.Platform, str]]] = ..., source_ids: _Optional[_Iterable[str]] = ..., fresh: _Optional[bool] = ...) -> None: ...

class StartSearchResponse(_message.Message):
    __slots__ = ("search",)
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    search: Search
    def __init__(self, search: _Optional[_Union[Search, _Mapping]] = ...) -> None: ...

class GetSearchRequest(_message.Message):
    __slots__ = ("context", "search_id")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ...) -> None: ...

class GetSearchResponse(_message.Message):
    __slots__ = ("search",)
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    search: Search
    def __init__(self, search: _Optional[_Union[Search, _Mapping]] = ...) -> None: ...

class ListSearchesRequest(_message.Message):
    __slots__ = ("context", "limit", "offset")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    limit: int
    offset: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListSearchesResponse(_message.Message):
    __slots__ = ("searches", "has_more")
    SEARCHES_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    searches: _containers.RepeatedCompositeFieldContainer[Search]
    has_more: bool
    def __init__(self, searches: _Optional[_Iterable[_Union[Search, _Mapping]]] = ..., has_more: _Optional[bool] = ...) -> None: ...

class RetrySearchRequest(_message.Message):
    __slots__ = ("context", "search_id", "target_ids")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_IDS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    target_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ..., target_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class RetrySearchResponse(_message.Message):
    __slots__ = ("search",)
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    search: Search
    def __init__(self, search: _Optional[_Union[Search, _Mapping]] = ...) -> None: ...

class CancelSearchRequest(_message.Message):
    __slots__ = ("context", "search_id")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ...) -> None: ...

class CancelSearchResponse(_message.Message):
    __slots__ = ("search",)
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    search: Search
    def __init__(self, search: _Optional[_Union[Search, _Mapping]] = ...) -> None: ...

class ResultSourceRef(_message.Message):
    __slots__ = ("source_id", "name", "url", "is_regional")
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    IS_REGIONAL_FIELD_NUMBER: _ClassVar[int]
    source_id: str
    name: str
    url: str
    is_regional: bool
    def __init__(self, source_id: _Optional[str] = ..., name: _Optional[str] = ..., url: _Optional[str] = ..., is_regional: _Optional[bool] = ...) -> None: ...

class ExcerptPart(_message.Message):
    __slots__ = ("text", "highlight")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FIELD_NUMBER: _ClassVar[int]
    text: str
    highlight: bool
    def __init__(self, text: _Optional[str] = ..., highlight: _Optional[bool] = ...) -> None: ...

class ResultRegion(_message.Message):
    __slots__ = ("by_source", "by_content", "evidence")
    BY_SOURCE_FIELD_NUMBER: _ClassVar[int]
    BY_CONTENT_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    by_source: bool
    by_content: bool
    evidence: str
    def __init__(self, by_source: _Optional[bool] = ..., by_content: _Optional[bool] = ..., evidence: _Optional[str] = ...) -> None: ...

class ResultMetrics(_message.Message):
    __slots__ = ("views", "likes", "reposts", "comments")
    VIEWS_FIELD_NUMBER: _ClassVar[int]
    LIKES_FIELD_NUMBER: _ClassVar[int]
    REPOSTS_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_FIELD_NUMBER: _ClassVar[int]
    views: int
    likes: int
    reposts: int
    comments: int
    def __init__(self, views: _Optional[int] = ..., likes: _Optional[int] = ..., reposts: _Optional[int] = ..., comments: _Optional[int] = ...) -> None: ...

class Result(_message.Message):
    __slots__ = ("id", "publication_id", "platform", "source", "url", "title", "title_source", "excerpt", "excerpt_parts", "published_at", "date_status", "relevance", "score", "explanation", "region", "sentiment", "group_id", "group_size", "metrics", "excluded", "found_by_target_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    PUBLICATION_ID_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    TITLE_SOURCE_FIELD_NUMBER: _ClassVar[int]
    EXCERPT_FIELD_NUMBER: _ClassVar[int]
    EXCERPT_PARTS_FIELD_NUMBER: _ClassVar[int]
    PUBLISHED_AT_FIELD_NUMBER: _ClassVar[int]
    DATE_STATUS_FIELD_NUMBER: _ClassVar[int]
    RELEVANCE_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    REGION_FIELD_NUMBER: _ClassVar[int]
    SENTIMENT_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    GROUP_SIZE_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDED_FIELD_NUMBER: _ClassVar[int]
    FOUND_BY_TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    publication_id: str
    platform: _platform_pb2.Platform
    source: ResultSourceRef
    url: str
    title: str
    title_source: TitleSource
    excerpt: str
    excerpt_parts: _containers.RepeatedCompositeFieldContainer[ExcerptPart]
    published_at: _timestamp_pb2.Timestamp
    date_status: DateStatus
    relevance: Relevance
    score: float
    explanation: str
    region: ResultRegion
    sentiment: Sentiment
    group_id: str
    group_size: int
    metrics: ResultMetrics
    excluded: bool
    found_by_target_id: str
    def __init__(self, id: _Optional[str] = ..., publication_id: _Optional[str] = ..., platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., source: _Optional[_Union[ResultSourceRef, _Mapping]] = ..., url: _Optional[str] = ..., title: _Optional[str] = ..., title_source: _Optional[_Union[TitleSource, str]] = ..., excerpt: _Optional[str] = ..., excerpt_parts: _Optional[_Iterable[_Union[ExcerptPart, _Mapping]]] = ..., published_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., date_status: _Optional[_Union[DateStatus, str]] = ..., relevance: _Optional[_Union[Relevance, str]] = ..., score: _Optional[float] = ..., explanation: _Optional[str] = ..., region: _Optional[_Union[ResultRegion, _Mapping]] = ..., sentiment: _Optional[_Union[Sentiment, str]] = ..., group_id: _Optional[str] = ..., group_size: _Optional[int] = ..., metrics: _Optional[_Union[ResultMetrics, _Mapping]] = ..., excluded: _Optional[bool] = ..., found_by_target_id: _Optional[str] = ...) -> None: ...

class ResultFilter(_message.Message):
    __slots__ = ("relevance", "platforms", "target_ids", "date_status", "include_excluded")
    RELEVANCE_FIELD_NUMBER: _ClassVar[int]
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    TARGET_IDS_FIELD_NUMBER: _ClassVar[int]
    DATE_STATUS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_EXCLUDED_FIELD_NUMBER: _ClassVar[int]
    relevance: _containers.RepeatedScalarFieldContainer[Relevance]
    platforms: _containers.RepeatedScalarFieldContainer[_platform_pb2.Platform]
    target_ids: _containers.RepeatedScalarFieldContainer[str]
    date_status: _containers.RepeatedScalarFieldContainer[DateStatus]
    include_excluded: bool
    def __init__(self, relevance: _Optional[_Iterable[_Union[Relevance, str]]] = ..., platforms: _Optional[_Iterable[_Union[_platform_pb2.Platform, str]]] = ..., target_ids: _Optional[_Iterable[str]] = ..., date_status: _Optional[_Iterable[_Union[DateStatus, str]]] = ..., include_excluded: _Optional[bool] = ...) -> None: ...

class ListResultsRequest(_message.Message):
    __slots__ = ("context", "search_id", "filter", "sort", "limit", "offset")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    filter: ResultFilter
    sort: ResultSort
    limit: int
    offset: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ..., filter: _Optional[_Union[ResultFilter, _Mapping]] = ..., sort: _Optional[_Union[ResultSort, str]] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListResultsResponse(_message.Message):
    __slots__ = ("results", "total", "has_more")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[Result]
    total: int
    has_more: bool
    def __init__(self, results: _Optional[_Iterable[_Union[Result, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: _Optional[bool] = ...) -> None: ...

class ResultGroup(_message.Message):
    __slots__ = ("group_id", "title", "size", "platforms", "earliest_published_at", "results")
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    EARLIEST_PUBLISHED_AT_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    group_id: str
    title: str
    size: int
    platforms: _containers.RepeatedScalarFieldContainer[_platform_pb2.Platform]
    earliest_published_at: _timestamp_pb2.Timestamp
    results: _containers.RepeatedCompositeFieldContainer[Result]
    def __init__(self, group_id: _Optional[str] = ..., title: _Optional[str] = ..., size: _Optional[int] = ..., platforms: _Optional[_Iterable[_Union[_platform_pb2.Platform, str]]] = ..., earliest_published_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., results: _Optional[_Iterable[_Union[Result, _Mapping]]] = ...) -> None: ...

class ListGroupsRequest(_message.Message):
    __slots__ = ("context", "search_id", "filter", "limit", "offset")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    filter: ResultFilter
    limit: int
    offset: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ..., filter: _Optional[_Union[ResultFilter, _Mapping]] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListGroupsResponse(_message.Message):
    __slots__ = ("groups", "total", "has_more")
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    groups: _containers.RepeatedCompositeFieldContainer[ResultGroup]
    total: int
    has_more: bool
    def __init__(self, groups: _Optional[_Iterable[_Union[ResultGroup, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: _Optional[bool] = ...) -> None: ...

class SetExcludedRequest(_message.Message):
    __slots__ = ("context", "search_id", "result_ids", "excluded")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    RESULT_IDS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDED_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    result_ids: _containers.RepeatedScalarFieldContainer[str]
    excluded: bool
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ..., result_ids: _Optional[_Iterable[str]] = ..., excluded: _Optional[bool] = ...) -> None: ...

class SetExcludedResponse(_message.Message):
    __slots__ = ("counts",)
    COUNTS_FIELD_NUMBER: _ClassVar[int]
    counts: SearchCounts
    def __init__(self, counts: _Optional[_Union[SearchCounts, _Mapping]] = ...) -> None: ...

class ExportSearchRequest(_message.Message):
    __slots__ = ("context", "search_id", "format", "filter", "sort")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SEARCH_ID_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    search_id: str
    format: ExportFormat
    filter: ResultFilter
    sort: ResultSort
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., search_id: _Optional[str] = ..., format: _Optional[_Union[ExportFormat, str]] = ..., filter: _Optional[_Union[ResultFilter, _Mapping]] = ..., sort: _Optional[_Union[ResultSort, str]] = ...) -> None: ...

class ExportSearchResponse(_message.Message):
    __slots__ = ("content", "filename", "mime_type")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    content: bytes
    filename: str
    mime_type: str
    def __init__(self, content: _Optional[bytes] = ..., filename: _Optional[str] = ..., mime_type: _Optional[str] = ...) -> None: ...

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

class PlatformHealth(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PLATFORM_HEALTH_UNSPECIFIED: _ClassVar[PlatformHealth]
    PLATFORM_HEALTH_OK: _ClassVar[PlatformHealth]
    PLATFORM_HEALTH_DEGRADED: _ClassVar[PlatformHealth]
    PLATFORM_HEALTH_UNAVAILABLE: _ClassVar[PlatformHealth]
PLATFORM_HEALTH_UNSPECIFIED: PlatformHealth
PLATFORM_HEALTH_OK: PlatformHealth
PLATFORM_HEALTH_DEGRADED: PlatformHealth
PLATFORM_HEALTH_UNAVAILABLE: PlatformHealth

class PlatformInfo(_message.Message):
    __slots__ = ("platform", "title", "source_mode_supported", "global_mode_supported", "health", "note")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_MODE_SUPPORTED_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_MODE_SUPPORTED_FIELD_NUMBER: _ClassVar[int]
    HEALTH_FIELD_NUMBER: _ClassVar[int]
    NOTE_FIELD_NUMBER: _ClassVar[int]
    platform: _platform_pb2.Platform
    title: str
    source_mode_supported: bool
    global_mode_supported: bool
    health: PlatformHealth
    note: str
    def __init__(self, platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., title: _Optional[str] = ..., source_mode_supported: _Optional[bool] = ..., global_mode_supported: _Optional[bool] = ..., health: _Optional[_Union[PlatformHealth, str]] = ..., note: _Optional[str] = ...) -> None: ...

class GetPlatformsRequest(_message.Message):
    __slots__ = ("context",)
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ...) -> None: ...

class GetPlatformsResponse(_message.Message):
    __slots__ = ("platforms",)
    PLATFORMS_FIELD_NUMBER: _ClassVar[int]
    platforms: _containers.RepeatedCompositeFieldContainer[PlatformInfo]
    def __init__(self, platforms: _Optional[_Iterable[_Union[PlatformInfo, _Mapping]]] = ...) -> None: ...

class SourceInfo(_message.Message):
    __slots__ = ("platform", "external_id", "screen_name", "url", "name", "city", "members_count", "is_closed")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    SCREEN_NAME_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_COUNT_FIELD_NUMBER: _ClassVar[int]
    IS_CLOSED_FIELD_NUMBER: _ClassVar[int]
    platform: _platform_pb2.Platform
    external_id: str
    screen_name: str
    url: str
    name: str
    city: str
    members_count: int
    is_closed: bool
    def __init__(self, platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., external_id: _Optional[str] = ..., screen_name: _Optional[str] = ..., url: _Optional[str] = ..., name: _Optional[str] = ..., city: _Optional[str] = ..., members_count: _Optional[int] = ..., is_closed: _Optional[bool] = ...) -> None: ...

class ResolveSourceRequest(_message.Message):
    __slots__ = ("context", "url")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    url: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., url: _Optional[str] = ...) -> None: ...

class ResolveSourceResponse(_message.Message):
    __slots__ = ("source",)
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    source: SourceInfo
    def __init__(self, source: _Optional[_Union[SourceInfo, _Mapping]] = ...) -> None: ...

class PostMetrics(_message.Message):
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

class RawPost(_message.Message):
    __slots__ = ("platform", "source_external_id", "source_name", "source_url", "post_external_id", "url", "title", "text", "published_at", "metrics", "is_repost", "repost_of_url", "fetched_at")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    SOURCE_EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_NAME_FIELD_NUMBER: _ClassVar[int]
    SOURCE_URL_FIELD_NUMBER: _ClassVar[int]
    POST_EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    PUBLISHED_AT_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    IS_REPOST_FIELD_NUMBER: _ClassVar[int]
    REPOST_OF_URL_FIELD_NUMBER: _ClassVar[int]
    FETCHED_AT_FIELD_NUMBER: _ClassVar[int]
    platform: _platform_pb2.Platform
    source_external_id: str
    source_name: str
    source_url: str
    post_external_id: str
    url: str
    title: str
    text: str
    published_at: _timestamp_pb2.Timestamp
    metrics: PostMetrics
    is_repost: bool
    repost_of_url: str
    fetched_at: _timestamp_pb2.Timestamp
    def __init__(self, platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., source_external_id: _Optional[str] = ..., source_name: _Optional[str] = ..., source_url: _Optional[str] = ..., post_external_id: _Optional[str] = ..., url: _Optional[str] = ..., title: _Optional[str] = ..., text: _Optional[str] = ..., published_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metrics: _Optional[_Union[PostMetrics, _Mapping]] = ..., is_repost: _Optional[bool] = ..., repost_of_url: _Optional[str] = ..., fetched_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CollectFromSourceRequest(_message.Message):
    __slots__ = ("context", "platform", "source_external_id", "period", "keywords", "max_posts")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    SOURCE_EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    KEYWORDS_FIELD_NUMBER: _ClassVar[int]
    MAX_POSTS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    platform: _platform_pb2.Platform
    source_external_id: str
    period: _platform_pb2.Period
    keywords: _containers.RepeatedScalarFieldContainer[str]
    max_posts: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., source_external_id: _Optional[str] = ..., period: _Optional[_Union[_platform_pb2.Period, _Mapping]] = ..., keywords: _Optional[_Iterable[str]] = ..., max_posts: _Optional[int] = ...) -> None: ...

class CollectFromSourceResponse(_message.Message):
    __slots__ = ("posts", "truncated", "warnings")
    POSTS_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    posts: _containers.RepeatedCompositeFieldContainer[RawPost]
    truncated: bool
    warnings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, posts: _Optional[_Iterable[_Union[RawPost, _Mapping]]] = ..., truncated: _Optional[bool] = ..., warnings: _Optional[_Iterable[str]] = ...) -> None: ...

class SearchPlatformRequest(_message.Message):
    __slots__ = ("context", "platform", "queries", "period", "region_terms", "max_posts")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    QUERIES_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    REGION_TERMS_FIELD_NUMBER: _ClassVar[int]
    MAX_POSTS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    platform: _platform_pb2.Platform
    queries: _containers.RepeatedScalarFieldContainer[str]
    period: _platform_pb2.Period
    region_terms: _containers.RepeatedScalarFieldContainer[str]
    max_posts: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., platform: _Optional[_Union[_platform_pb2.Platform, str]] = ..., queries: _Optional[_Iterable[str]] = ..., period: _Optional[_Union[_platform_pb2.Period, _Mapping]] = ..., region_terms: _Optional[_Iterable[str]] = ..., max_posts: _Optional[int] = ...) -> None: ...

class SearchPlatformResponse(_message.Message):
    __slots__ = ("posts", "truncated", "warnings")
    POSTS_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    posts: _containers.RepeatedCompositeFieldContainer[RawPost]
    truncated: bool
    warnings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, posts: _Optional[_Iterable[_Union[RawPost, _Mapping]]] = ..., truncated: _Optional[bool] = ..., warnings: _Optional[_Iterable[str]] = ...) -> None: ...

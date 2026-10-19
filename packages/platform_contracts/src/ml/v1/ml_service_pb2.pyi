from common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class QueryType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    QUERY_TYPE_UNSPECIFIED: _ClassVar[QueryType]
    QUERY_TYPE_TOPIC: _ClassVar[QueryType]
    QUERY_TYPE_EVENT: _ClassVar[QueryType]
    QUERY_TYPE_PERSON: _ClassVar[QueryType]
    QUERY_TYPE_NEWS_TEXT: _ClassVar[QueryType]

class EntityType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ENTITY_TYPE_UNSPECIFIED: _ClassVar[EntityType]
    ENTITY_TYPE_PERSON: _ClassVar[EntityType]
    ENTITY_TYPE_ORGANIZATION: _ClassVar[EntityType]
    ENTITY_TYPE_LOCATION: _ClassVar[EntityType]
    ENTITY_TYPE_EVENT: _ClassVar[EntityType]
    ENTITY_TYPE_DATE: _ClassVar[EntityType]
    ENTITY_TYPE_NUMBER: _ClassVar[EntityType]

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
QUERY_TYPE_UNSPECIFIED: QueryType
QUERY_TYPE_TOPIC: QueryType
QUERY_TYPE_EVENT: QueryType
QUERY_TYPE_PERSON: QueryType
QUERY_TYPE_NEWS_TEXT: QueryType
ENTITY_TYPE_UNSPECIFIED: EntityType
ENTITY_TYPE_PERSON: EntityType
ENTITY_TYPE_ORGANIZATION: EntityType
ENTITY_TYPE_LOCATION: EntityType
ENTITY_TYPE_EVENT: EntityType
ENTITY_TYPE_DATE: EntityType
ENTITY_TYPE_NUMBER: EntityType
RELEVANCE_UNSPECIFIED: Relevance
RELEVANCE_DIRECT: Relevance
RELEVANCE_INDIRECT: Relevance
RELEVANCE_DISPUTED: Relevance
RELEVANCE_IRRELEVANT: Relevance
SENTIMENT_UNSPECIFIED: Sentiment
SENTIMENT_POSITIVE: Sentiment
SENTIMENT_NEUTRAL: Sentiment
SENTIMENT_NEGATIVE: Sentiment

class Entity(_message.Message):
    __slots__ = ("text", "type")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    text: str
    type: EntityType
    def __init__(self, text: _Optional[str] = ..., type: _Optional[_Union[EntityType, str]] = ...) -> None: ...

class QueryAnalysis(_message.Message):
    __slots__ = ("query_type", "summary", "search_queries", "entities", "must_concepts", "exclude_concepts", "needs_clarification", "clarification_hint")
    QUERY_TYPE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    SEARCH_QUERIES_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    MUST_CONCEPTS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDE_CONCEPTS_FIELD_NUMBER: _ClassVar[int]
    NEEDS_CLARIFICATION_FIELD_NUMBER: _ClassVar[int]
    CLARIFICATION_HINT_FIELD_NUMBER: _ClassVar[int]
    query_type: QueryType
    summary: str
    search_queries: _containers.RepeatedScalarFieldContainer[str]
    entities: _containers.RepeatedCompositeFieldContainer[Entity]
    must_concepts: _containers.RepeatedScalarFieldContainer[str]
    exclude_concepts: _containers.RepeatedScalarFieldContainer[str]
    needs_clarification: bool
    clarification_hint: str
    def __init__(self, query_type: _Optional[_Union[QueryType, str]] = ..., summary: _Optional[str] = ..., search_queries: _Optional[_Iterable[str]] = ..., entities: _Optional[_Iterable[_Union[Entity, _Mapping]]] = ..., must_concepts: _Optional[_Iterable[str]] = ..., exclude_concepts: _Optional[_Iterable[str]] = ..., needs_clarification: _Optional[bool] = ..., clarification_hint: _Optional[str] = ...) -> None: ...

class AnalyzeQueryRequest(_message.Message):
    __slots__ = ("context", "query")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    query: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., query: _Optional[str] = ...) -> None: ...

class AnalyzeQueryResponse(_message.Message):
    __slots__ = ("analysis", "degraded")
    ANALYSIS_FIELD_NUMBER: _ClassVar[int]
    DEGRADED_FIELD_NUMBER: _ClassVar[int]
    analysis: QueryAnalysis
    degraded: bool
    def __init__(self, analysis: _Optional[_Union[QueryAnalysis, _Mapping]] = ..., degraded: _Optional[bool] = ...) -> None: ...

class TextSpan(_message.Message):
    __slots__ = ("start", "end")
    START_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    start: int
    end: int
    def __init__(self, start: _Optional[int] = ..., end: _Optional[int] = ...) -> None: ...

class PostForScoring(_message.Message):
    __slots__ = ("id", "title", "text", "source_name", "source_is_regional")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_NAME_FIELD_NUMBER: _ClassVar[int]
    SOURCE_IS_REGIONAL_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    text: str
    source_name: str
    source_is_regional: bool
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., text: _Optional[str] = ..., source_name: _Optional[str] = ..., source_is_regional: _Optional[bool] = ...) -> None: ...

class RegionMatch(_message.Message):
    __slots__ = ("by_content", "evidence")
    BY_CONTENT_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    by_content: bool
    evidence: str
    def __init__(self, by_content: _Optional[bool] = ..., evidence: _Optional[str] = ...) -> None: ...

class PostScore(_message.Message):
    __slots__ = ("id", "relevance", "score", "explanation", "region", "sentiment", "excerpt_span", "highlight_spans")
    ID_FIELD_NUMBER: _ClassVar[int]
    RELEVANCE_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    REGION_FIELD_NUMBER: _ClassVar[int]
    SENTIMENT_FIELD_NUMBER: _ClassVar[int]
    EXCERPT_SPAN_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_SPANS_FIELD_NUMBER: _ClassVar[int]
    id: str
    relevance: Relevance
    score: float
    explanation: str
    region: RegionMatch
    sentiment: Sentiment
    excerpt_span: TextSpan
    highlight_spans: _containers.RepeatedCompositeFieldContainer[TextSpan]
    def __init__(self, id: _Optional[str] = ..., relevance: _Optional[_Union[Relevance, str]] = ..., score: _Optional[float] = ..., explanation: _Optional[str] = ..., region: _Optional[_Union[RegionMatch, _Mapping]] = ..., sentiment: _Optional[_Union[Sentiment, str]] = ..., excerpt_span: _Optional[_Union[TextSpan, _Mapping]] = ..., highlight_spans: _Optional[_Iterable[_Union[TextSpan, _Mapping]]] = ...) -> None: ...

class ScorePostsRequest(_message.Message):
    __slots__ = ("context", "query", "analysis", "posts")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    ANALYSIS_FIELD_NUMBER: _ClassVar[int]
    POSTS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    query: str
    analysis: QueryAnalysis
    posts: _containers.RepeatedCompositeFieldContainer[PostForScoring]
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., query: _Optional[str] = ..., analysis: _Optional[_Union[QueryAnalysis, _Mapping]] = ..., posts: _Optional[_Iterable[_Union[PostForScoring, _Mapping]]] = ...) -> None: ...

class ScorePostsResponse(_message.Message):
    __slots__ = ("scores", "degraded")
    SCORES_FIELD_NUMBER: _ClassVar[int]
    DEGRADED_FIELD_NUMBER: _ClassVar[int]
    scores: _containers.RepeatedCompositeFieldContainer[PostScore]
    degraded: bool
    def __init__(self, scores: _Optional[_Iterable[_Union[PostScore, _Mapping]]] = ..., degraded: _Optional[bool] = ...) -> None: ...

class PostForGrouping(_message.Message):
    __slots__ = ("id", "title", "text")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    text: str
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., text: _Optional[str] = ...) -> None: ...

class PostGroup(_message.Message):
    __slots__ = ("group_id", "post_ids", "representative_post_id")
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    POST_IDS_FIELD_NUMBER: _ClassVar[int]
    REPRESENTATIVE_POST_ID_FIELD_NUMBER: _ClassVar[int]
    group_id: str
    post_ids: _containers.RepeatedScalarFieldContainer[str]
    representative_post_id: str
    def __init__(self, group_id: _Optional[str] = ..., post_ids: _Optional[_Iterable[str]] = ..., representative_post_id: _Optional[str] = ...) -> None: ...

class GroupPostsRequest(_message.Message):
    __slots__ = ("context", "posts")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    POSTS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    posts: _containers.RepeatedCompositeFieldContainer[PostForGrouping]
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., posts: _Optional[_Iterable[_Union[PostForGrouping, _Mapping]]] = ...) -> None: ...

class GroupPostsResponse(_message.Message):
    __slots__ = ("groups",)
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    groups: _containers.RepeatedCompositeFieldContainer[PostGroup]
    def __init__(self, groups: _Optional[_Iterable[_Union[PostGroup, _Mapping]]] = ...) -> None: ...

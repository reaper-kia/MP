"""gRPC-клиент к ml_service: proto ⇄ DTO порта, ошибки → UpstreamError.

Реализует порт applications/ports/ml_client.py (им пользуется пайплайн B2).
"""

from typing import Any

import grpc
from ml.v1 import ml_service_pb2 as pb
from ml.v1 import ml_service_pb2_grpc as pb_grpc

from search_service.applications.ports.ml_client import (
    MlClient,
    PostForScoring,
    PostGroup,
    PostScore,
    QueryAnalysis,
)
from search_service.domain.enums import QueryType, Relevance, Sentiment
from search_service.infra.clients.common import context_to_proto, upstream_error

QUERY_TYPE_TO_PROTO: dict[QueryType, pb.QueryType] = {
    QueryType.TOPIC: pb.QUERY_TYPE_TOPIC,
    QueryType.EVENT: pb.QUERY_TYPE_EVENT,
    QueryType.PERSON: pb.QUERY_TYPE_PERSON,
    QueryType.NEWS_TEXT: pb.QUERY_TYPE_NEWS_TEXT,
}
QUERY_TYPE_FROM_PROTO: dict[int, QueryType] = {v: k for k, v in QUERY_TYPE_TO_PROTO.items()}

ENTITY_TYPE_TO_PROTO: dict[str, pb.EntityType] = {
    "person": pb.ENTITY_TYPE_PERSON,
    "organization": pb.ENTITY_TYPE_ORGANIZATION,
    "location": pb.ENTITY_TYPE_LOCATION,
    "event": pb.ENTITY_TYPE_EVENT,
    "date": pb.ENTITY_TYPE_DATE,
    "number": pb.ENTITY_TYPE_NUMBER,
}
ENTITY_TYPE_FROM_PROTO: dict[int, str] = {v: k for k, v in ENTITY_TYPE_TO_PROTO.items()}

RELEVANCE_FROM_PROTO: dict[int, Relevance] = {
    pb.RELEVANCE_DIRECT: Relevance.DIRECT,
    pb.RELEVANCE_INDIRECT: Relevance.INDIRECT,
    pb.RELEVANCE_DISPUTED: Relevance.DISPUTED,
    pb.RELEVANCE_IRRELEVANT: Relevance.IRRELEVANT,
}
SENTIMENT_FROM_PROTO: dict[int, Sentiment] = {
    pb.SENTIMENT_POSITIVE: Sentiment.POSITIVE,
    pb.SENTIMENT_NEUTRAL: Sentiment.NEUTRAL,
    pb.SENTIMENT_NEGATIVE: Sentiment.NEGATIVE,
}


class GrpcMlClient(MlClient):
    def __init__(
        self,
        channel: grpc.aio.Channel,
        analyze_timeout: float,
        score_timeout: float,
        group_timeout: float,
    ) -> None:
        self._stub = pb_grpc.MlServiceStub(channel)
        self._analyze_timeout = analyze_timeout
        self._score_timeout = score_timeout
        self._group_timeout = group_timeout

    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]:
        try:
            response: pb.AnalyzeQueryResponse = await self._stub.AnalyzeQuery(
                pb.AnalyzeQueryRequest(context=context_to_proto(), query=query),
                timeout=self._analyze_timeout,
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("ml", e) from e
        return analysis_from_proto(response.analysis, query), response.degraded

    async def score_posts(
        self, *, query: str, analysis: QueryAnalysis, posts: list[PostForScoring]
    ) -> tuple[list[PostScore], bool]:
        request = pb.ScorePostsRequest(
            context=context_to_proto(),
            query=query,
            analysis=analysis_to_proto(analysis),
            posts=[_post_for_scoring(p) for p in posts],
        )
        try:
            response: pb.ScorePostsResponse = await self._stub.ScorePosts(
                request, timeout=self._score_timeout
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("ml", e) from e
        return [_score(s) for s in response.scores], response.degraded

    async def group_posts(self, posts: list[dict[str, Any]]) -> list[PostGroup]:
        """posts — {"id", "text", "title"} (так их собирает ScoringHandler.group_search)."""
        request = pb.GroupPostsRequest(
            context=context_to_proto(),
            posts=[_post_for_grouping(p) for p in posts],
        )
        try:
            response: pb.GroupPostsResponse = await self._stub.GroupPosts(
                request, timeout=self._group_timeout
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("ml", e) from e
        return [
            PostGroup(
                group_id=g.group_id,
                post_ids=list(g.post_ids),
                representative_post_id=g.representative_post_id,
            )
            for g in response.groups
        ]


def _query_type(value: str) -> QueryType:
    try:
        return QueryType(value)
    except ValueError:
        return QueryType.TOPIC


def analysis_from_proto(a: pb.QueryAnalysis, query: str) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=QUERY_TYPE_FROM_PROTO.get(a.query_type, QueryType.TOPIC).value,
        summary=a.summary,
        search_queries=list(a.search_queries) or [query],
        entities=[
            {"text": e.text, "type": ENTITY_TYPE_FROM_PROTO[e.type]}
            for e in a.entities
            if e.type in ENTITY_TYPE_FROM_PROTO
        ],
        must_concepts=list(a.must_concepts),
        exclude_concepts=list(a.exclude_concepts),
        needs_clarification=a.needs_clarification,
        clarification_hint=a.clarification_hint,
    )


def analysis_to_proto(a: QueryAnalysis) -> pb.QueryAnalysis:
    return pb.QueryAnalysis(
        query_type=QUERY_TYPE_TO_PROTO[_query_type(a.query_type)],
        summary=a.summary,
        search_queries=list(a.search_queries),
        entities=[
            pb.Entity(text=str(e.get("text", "")), type=ENTITY_TYPE_TO_PROTO[str(e.get("type"))])
            for e in a.entities
            if str(e.get("type")) in ENTITY_TYPE_TO_PROTO
        ],
        must_concepts=list(a.must_concepts),
        exclude_concepts=list(a.exclude_concepts),
        needs_clarification=a.needs_clarification,
        clarification_hint=a.clarification_hint,
    )


def _post_for_scoring(p: PostForScoring) -> pb.PostForScoring:
    message = pb.PostForScoring(
        id=p.id, text=p.text, source_name=p.source_name, source_is_regional=p.source_is_regional
    )
    if p.title is not None:
        message.title = p.title
    return message


def _post_for_grouping(p: dict[str, Any]) -> pb.PostForGrouping:
    message = pb.PostForGrouping(id=str(p["id"]), text=str(p.get("text") or ""))
    if p.get("title") is not None:
        message.title = str(p["title"])
    return message


def _score(s: pb.PostScore) -> PostScore:
    sentiment = SENTIMENT_FROM_PROTO.get(s.sentiment)
    return PostScore(
        id=s.id,
        relevance=RELEVANCE_FROM_PROTO.get(s.relevance, Relevance.DISPUTED).value,
        score=s.score,
        explanation=s.explanation,
        region_by_content=s.region.by_content,
        region_evidence=s.region.evidence,
        sentiment=sentiment.value if sentiment is not None else None,
        excerpt_span=(
            (s.excerpt_span.start, s.excerpt_span.end) if s.HasField("excerpt_span") else None
        ),
        highlight_spans=[(h.start, h.end) for h in s.highlight_spans],
    )

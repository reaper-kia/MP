"""proto ⇄ core.models. Единственное место, где core встречается с proto."""

from ml.v1 import ml_service_pb2 as pb

from ml_service.core.models import (
    Entity,
    EntityType,
    GroupInput,
    Post,
    PostGroup,
    PostScore,
    QueryAnalysis,
    QueryType,
    Relevance,
    Sentiment,
    Span,
)

QUERY_TYPE_TO_PROTO: dict[QueryType, pb.QueryType] = {
    QueryType.TOPIC: pb.QUERY_TYPE_TOPIC,
    QueryType.EVENT: pb.QUERY_TYPE_EVENT,
    QueryType.PERSON: pb.QUERY_TYPE_PERSON,
    QueryType.NEWS_TEXT: pb.QUERY_TYPE_NEWS_TEXT,
}
QUERY_TYPE_FROM_PROTO: dict[int, QueryType] = {v: k for k, v in QUERY_TYPE_TO_PROTO.items()}

ENTITY_TYPE_TO_PROTO: dict[EntityType, pb.EntityType] = {
    EntityType.PERSON: pb.ENTITY_TYPE_PERSON,
    EntityType.ORGANIZATION: pb.ENTITY_TYPE_ORGANIZATION,
    EntityType.LOCATION: pb.ENTITY_TYPE_LOCATION,
    EntityType.EVENT: pb.ENTITY_TYPE_EVENT,
    EntityType.DATE: pb.ENTITY_TYPE_DATE,
    EntityType.NUMBER: pb.ENTITY_TYPE_NUMBER,
}
ENTITY_TYPE_FROM_PROTO: dict[int, EntityType] = {v: k for k, v in ENTITY_TYPE_TO_PROTO.items()}

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


def analysis_to_proto(a: QueryAnalysis) -> pb.QueryAnalysis:
    return pb.QueryAnalysis(
        query_type=QUERY_TYPE_TO_PROTO[a.query_type],
        summary=a.summary,
        search_queries=list(a.search_queries),
        entities=[pb.Entity(text=e.text, type=ENTITY_TYPE_TO_PROTO[e.type]) for e in a.entities],
        must_concepts=list(a.must_concepts),
        exclude_concepts=list(a.exclude_concepts),
        needs_clarification=a.needs_clarification,
        clarification_hint=a.clarification_hint,
    )


def analysis_from_proto(a: pb.QueryAnalysis, query: str) -> QueryAnalysis:
    """B2 присылает то, что получил из AnalyzeQuery. Пустой analysis → тема = сам запрос."""
    return QueryAnalysis(
        query_type=QUERY_TYPE_FROM_PROTO.get(a.query_type, QueryType.TOPIC),
        summary=a.summary,
        search_queries=list(a.search_queries) or [query],
        entities=[
            Entity(text=e.text, type=ENTITY_TYPE_FROM_PROTO[e.type])
            for e in a.entities
            if e.type in ENTITY_TYPE_FROM_PROTO
        ],
        must_concepts=list(a.must_concepts),
        exclude_concepts=list(a.exclude_concepts),
        needs_clarification=a.needs_clarification,
        clarification_hint=a.clarification_hint,
    )


def post_from_proto(p: pb.PostForScoring) -> Post:
    return Post(
        id=p.id,
        text=p.text,
        title=p.title if p.HasField("title") else None,
        source_name=p.source_name,
        source_is_regional=p.source_is_regional,
    )


def span_to_proto(s: Span) -> pb.TextSpan:
    return pb.TextSpan(start=s.start, end=s.end)


def score_to_proto(s: PostScore) -> pb.PostScore:
    return pb.PostScore(
        id=s.id,
        relevance=RELEVANCE_TO_PROTO[s.relevance],
        score=s.score,
        explanation=s.explanation,
        region=pb.RegionMatch(by_content=s.region_by_content, evidence=s.region_evidence),
        sentiment=(
            SENTIMENT_TO_PROTO[s.sentiment] if s.sentiment is not None else pb.SENTIMENT_UNSPECIFIED
        ),
        excerpt_span=span_to_proto(s.excerpt_span),
        highlight_spans=[span_to_proto(h) for h in s.highlight_spans],
    )


def group_input_from_proto(p: pb.PostForGrouping) -> GroupInput:
    return GroupInput(id=p.id, text=p.text, title=p.title if p.HasField("title") else None)


def group_to_proto(g: PostGroup) -> pb.PostGroup:
    return pb.PostGroup(
        group_id=g.group_id,
        post_ids=list(g.post_ids),
        representative_post_id=g.representative_post_id,
    )

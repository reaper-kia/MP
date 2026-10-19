"""Enum'ы HTTP (строки из openapi.yaml) ⇄ proto. Одно место для всех роутеров (TL-03).

Правило: убрать префикс и в нижний регистр. Исключения: RELEVANCE_IRRELEVANT ⇄ "rejected",
*_UNSPECIFIED → None.
"""

from typing import Literal

from collector.v1 import collector_service_pb2 as collector_pb
from common.v1 import platform_pb2
from ml.v1 import ml_service_pb2 as ml_pb
from search.v1 import search_service_pb2 as pb

Platform = Literal["vk", "ok", "max", "news"]
QueryType = Literal["topic", "event", "person", "news_text"]
SearchMode = Literal["selected", "global"]
SearchStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
SearchStage = Literal["queued", "analyzing_query", "collecting", "scoring", "grouping", "done"]
TargetKind = Literal["source", "platform_search"]
TargetStatus = Literal["pending", "running", "done", "empty", "failed", "skipped"]
Relevance = Literal["direct", "indirect", "disputed", "rejected"]
Sentiment = Literal["positive", "neutral", "negative"]
TitleSource = Literal["title", "post_start"]
DateStatus = Literal["in_period", "unknown"]
ResultSort = Literal["relevance", "date_desc", "date_asc"]
ExportFormat = Literal["xlsx", "docx"]
PlatformHealth = Literal["ok", "degraded", "unavailable"]

PLATFORM_TO_PROTO: dict[str, platform_pb2.Platform] = {
    "vk": platform_pb2.PLATFORM_VK,
    "ok": platform_pb2.PLATFORM_OK,
    "max": platform_pb2.PLATFORM_MAX,
    "news": platform_pb2.PLATFORM_NEWS,
}
PLATFORM_FROM_PROTO: dict[int, Platform] = {
    platform_pb2.PLATFORM_VK: "vk",
    platform_pb2.PLATFORM_OK: "ok",
    platform_pb2.PLATFORM_MAX: "max",
    platform_pb2.PLATFORM_NEWS: "news",
}

HEALTH_FROM_PROTO: dict[int, PlatformHealth] = {
    collector_pb.PLATFORM_HEALTH_OK: "ok",
    collector_pb.PLATFORM_HEALTH_DEGRADED: "degraded",
    collector_pb.PLATFORM_HEALTH_UNAVAILABLE: "unavailable",
}

QUERY_TYPE_FROM_PROTO: dict[int, QueryType] = {
    pb.QUERY_TYPE_TOPIC: "topic",
    pb.QUERY_TYPE_EVENT: "event",
    pb.QUERY_TYPE_PERSON: "person",
    pb.QUERY_TYPE_NEWS_TEXT: "news_text",
}
ML_QUERY_TYPE_FROM_PROTO: dict[int, QueryType] = {
    ml_pb.QUERY_TYPE_TOPIC: "topic",
    ml_pb.QUERY_TYPE_EVENT: "event",
    ml_pb.QUERY_TYPE_PERSON: "person",
    ml_pb.QUERY_TYPE_NEWS_TEXT: "news_text",
}

MODE_TO_PROTO: dict[str, pb.SearchMode] = {
    "selected": pb.SEARCH_MODE_SELECTED,
    "global": pb.SEARCH_MODE_GLOBAL,
}
MODE_FROM_PROTO: dict[int, SearchMode] = {
    pb.SEARCH_MODE_SELECTED: "selected",
    pb.SEARCH_MODE_GLOBAL: "global",
}

STATUS_FROM_PROTO: dict[int, SearchStatus] = {
    pb.SEARCH_STATUS_QUEUED: "queued",
    pb.SEARCH_STATUS_RUNNING: "running",
    pb.SEARCH_STATUS_COMPLETED: "completed",
    pb.SEARCH_STATUS_PARTIAL: "partial",
    pb.SEARCH_STATUS_FAILED: "failed",
    pb.SEARCH_STATUS_CANCELLED: "cancelled",
}
STAGE_FROM_PROTO: dict[int, SearchStage] = {
    pb.SEARCH_STAGE_QUEUED: "queued",
    pb.SEARCH_STAGE_ANALYZING_QUERY: "analyzing_query",
    pb.SEARCH_STAGE_COLLECTING: "collecting",
    pb.SEARCH_STAGE_SCORING: "scoring",
    pb.SEARCH_STAGE_GROUPING: "grouping",
    pb.SEARCH_STAGE_DONE: "done",
}
TARGET_KIND_FROM_PROTO: dict[int, TargetKind] = {
    pb.TARGET_KIND_SOURCE: "source",
    pb.TARGET_KIND_PLATFORM_SEARCH: "platform_search",
}
TARGET_STATUS_FROM_PROTO: dict[int, TargetStatus] = {
    pb.TARGET_STATUS_PENDING: "pending",
    pb.TARGET_STATUS_RUNNING: "running",
    pb.TARGET_STATUS_DONE: "done",
    pb.TARGET_STATUS_EMPTY: "empty",
    pb.TARGET_STATUS_FAILED: "failed",
    pb.TARGET_STATUS_SKIPPED: "skipped",
}

RELEVANCE_TO_PROTO: dict[str, pb.Relevance] = {
    "direct": pb.RELEVANCE_DIRECT,
    "indirect": pb.RELEVANCE_INDIRECT,
    "disputed": pb.RELEVANCE_DISPUTED,
    "rejected": pb.RELEVANCE_IRRELEVANT,
}
RELEVANCE_FROM_PROTO: dict[int, Relevance] = {
    pb.RELEVANCE_DIRECT: "direct",
    pb.RELEVANCE_INDIRECT: "indirect",
    pb.RELEVANCE_DISPUTED: "disputed",
    pb.RELEVANCE_IRRELEVANT: "rejected",
}
SENTIMENT_FROM_PROTO: dict[int, Sentiment] = {
    pb.SENTIMENT_POSITIVE: "positive",
    pb.SENTIMENT_NEUTRAL: "neutral",
    pb.SENTIMENT_NEGATIVE: "negative",
}
TITLE_SOURCE_FROM_PROTO: dict[int, TitleSource] = {
    pb.TITLE_SOURCE_TITLE: "title",
    pb.TITLE_SOURCE_POST_START: "post_start",
}
DATE_STATUS_TO_PROTO: dict[str, pb.DateStatus] = {
    "in_period": pb.DATE_STATUS_IN_PERIOD,
    "unknown": pb.DATE_STATUS_UNKNOWN,
}
DATE_STATUS_FROM_PROTO: dict[int, DateStatus] = {
    pb.DATE_STATUS_IN_PERIOD: "in_period",
    pb.DATE_STATUS_UNKNOWN: "unknown",
}
SORT_TO_PROTO: dict[str, pb.ResultSort] = {
    "relevance": pb.RESULT_SORT_RELEVANCE,
    "date_desc": pb.RESULT_SORT_DATE_DESC,
    "date_asc": pb.RESULT_SORT_DATE_ASC,
}
FORMAT_TO_PROTO: dict[str, pb.ExportFormat] = {
    "xlsx": pb.EXPORT_FORMAT_XLSX,
    "docx": pb.EXPORT_FORMAT_DOCX,
}

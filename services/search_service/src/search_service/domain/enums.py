"""Перечисления домена. Значения — как в HTTP API (docs/API.md), маппинг в proto — transport/."""

from enum import StrEnum


class Platform(StrEnum):
    VK = "vk"
    OK = "ok"
    MAX = "max"
    NEWS = "news"

    @property
    def display(self) -> str:
        return {"vk": "VK", "ok": "Одноклассники", "max": "MAX", "news": "Новостные сайты"}[
            self.value
        ]


class SearchMode(StrEnum):
    SELECTED = "selected"
    GLOBAL = "global"


class SearchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in FINAL_SEARCH_STATUSES


FINAL_SEARCH_STATUSES = frozenset(
    {SearchStatus.COMPLETED, SearchStatus.PARTIAL, SearchStatus.FAILED, SearchStatus.CANCELLED}
)


class SearchStage(StrEnum):
    QUEUED = "queued"
    ANALYZING_QUERY = "analyzing_query"
    COLLECTING = "collecting"
    SCORING = "scoring"
    GROUPING = "grouping"
    DONE = "done"


class QueryType(StrEnum):
    TOPIC = "topic"
    EVENT = "event"
    PERSON = "person"
    NEWS_TEXT = "news_text"


class TargetKind(StrEnum):
    SOURCE = "source"
    PLATFORM_SEARCH = "platform_search"


class TargetStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    EMPTY = "empty"
    FAILED = "failed"
    SKIPPED = "skipped"


class Relevance(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    DISPUTED = "disputed"
    IRRELEVANT = "irrelevant"  # в HTTP — "rejected"


IN_SELECTION = frozenset({Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED})


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class TitleSource(StrEnum):
    TITLE = "title"
    POST_START = "post_start"


class DateStatus(StrEnum):
    IN_PERIOD = "in_period"
    UNKNOWN = "unknown"


class ResultSort(StrEnum):
    RELEVANCE = "relevance"
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    DOCX = "docx"


TERMINAL_TARGETS = frozenset(
    {TargetStatus.DONE, TargetStatus.EMPTY, TargetStatus.FAILED, TargetStatus.SKIPPED}
)
TERMINAL_SEARCHES = FINAL_SEARCH_STATUSES

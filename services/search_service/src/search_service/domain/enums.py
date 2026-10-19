from enum import StrEnum

class Platform(StrEnum):
    VK = "vk"
    OK = "ok"
    MAX = "max"
    NEWS = "news"

    @property
    def display(self) -> str:
        return {"vk": "VK", "ok": "Одноклассники", "max": "MAX", "news": "Новостные сайты"}[self.value]

class SearchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SearchStage(StrEnum):
    ANALYZING_QUERY = "analyzing_query"
    COLLECTING = "collecting"
    SCORING = "scoring"
    GROUPING = "grouping"
    DONE = "done"

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
    IRRELEVANT = "irrelevant"

class DateStatus(StrEnum):
    IN_PERIOD = "in_period"
    UNKNOWN = "unknown"

class SearchMode(StrEnum):
    SELECTED = "selected"
    GLOBAL = "global"

class TitleSource(StrEnum):
    TITLE = "title"
    POST_START = "post_start"

class TargetKind(StrEnum):
    SOURCE = "source"
    PLATFORM = "platform"

TERMINAL_TARGETS = frozenset({TargetStatus.DONE, TargetStatus.EMPTY, TargetStatus.FAILED, TargetStatus.SKIPPED})
TERMINAL_SEARCHES = frozenset({SearchStatus.COMPLETED, SearchStatus.PARTIAL, SearchStatus.FAILED, SearchStatus.CANCELLED})
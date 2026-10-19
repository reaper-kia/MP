from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectLimits:
    """Сколько постов отдавать, если в запросе max_posts = 0 (значения — из настроек сервиса)."""

    per_source: int
    per_search: int

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectLimits:
    """Лимиты сбора (значения — из настроек сервиса).

    per_source / per_search — сколько постов отдавать, если в запросе max_posts = 0;
    budget_seconds — сколько времени даём одному сбору, после этого отдаём то, что успели.
    """

    per_source: int
    per_search: int
    budget_seconds: float = 50.0

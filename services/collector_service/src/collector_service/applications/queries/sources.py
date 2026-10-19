from collections.abc import Sequence
from dataclasses import dataclass, field

from collector_service.applications.context import RequestContext
from collector_service.applications.mediator import Query
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.domain.urls import normalize_url
from collector_service.domain.value_objects import CollectResult, Period, SourceInfo


@dataclass(frozen=True)
class ResolveSourceQuery(Query[SourceInfo]):
    ctx: RequestContext
    url: str

    def cache_key(self) -> str | None:
        """Кэш resolve на 10 минут (B1-09 п. 1): одна и та же группа — один запрос к площадке."""
        try:
            return "resolve:" + normalize_url(self.url).lower()
        except UnsupportedUrlError:
            return None


@dataclass(frozen=True)
class CollectFromSourceQuery(Query[CollectResult]):
    """Режим «по выбранным источникам»: посты одного источника за период."""

    ctx: RequestContext
    platform: Platform
    source_external_id: str
    period: Period
    keywords: Sequence[str] = field(default_factory=list)
    max_posts: int = 0  # 0 — по умолчанию (CollectLimits.per_source)

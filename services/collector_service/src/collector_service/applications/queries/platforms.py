from collections.abc import Sequence
from dataclasses import dataclass, field

from collector_service.applications.context import RequestContext
from collector_service.applications.mediator import Query
from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import CollectResult, Period, PlatformInfo


@dataclass(frozen=True)
class GetPlatformsQuery(Query[list[PlatformInfo]]):
    ctx: RequestContext


@dataclass(frozen=True)
class SearchPlatformQuery(Query[CollectResult]):
    """Режим «без ограничения списком»: поиск по всей площадке."""

    ctx: RequestContext
    platform: Platform
    queries: Sequence[str]
    period: Period
    region_terms: Sequence[str] = field(default_factory=list)
    max_posts: int = 0  # 0 — по умолчанию (CollectLimits.per_search)

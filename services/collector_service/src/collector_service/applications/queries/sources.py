from collections.abc import Sequence
from dataclasses import dataclass, field

from collector_service.applications.context import RequestContext
from collector_service.applications.mediator import Command
from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import CollectResult, Period, SourceInfo


@dataclass(frozen=True)
class ResolveSourceQuery(Command[SourceInfo]):
    ctx: RequestContext
    url: str


@dataclass(frozen=True)
class CollectFromSourceQuery(Command[CollectResult]):
    """Режим «по выбранным источникам»: посты одного источника за период."""

    ctx: RequestContext
    platform: Platform
    source_external_id: str
    period: Period
    keywords: Sequence[str] = field(default_factory=list)
    max_posts: int = 0  # 0 — по умолчанию (CollectLimits.per_source)

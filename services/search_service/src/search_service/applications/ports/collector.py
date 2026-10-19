"""Порт к collector_service. Реализация — infra/clients/collector_client.py, фейк — tests/fakes.py.

Ошибки соседа приходят как applications.exceptions.UpstreamError(code=...).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from search_service.applications.context import RequestContext
from search_service.domain.enums import Platform
from search_service.domain.value_objects import UtcPeriod


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    platform: Platform
    title: str
    source_mode_supported: bool
    global_mode_supported: bool
    health: str  # ok | degraded | unavailable
    note: str


@dataclass(frozen=True, slots=True)
class SourceInfo:
    platform: Platform
    external_id: str
    screen_name: str
    url: str
    name: str
    city: str | None
    members_count: int | None
    is_closed: bool


@dataclass(frozen=True, slots=True)
class PostMetrics:
    views: int | None = None
    likes: int | None = None
    reposts: int | None = None
    comments: int | None = None


@dataclass(frozen=True, slots=True)
class RawPost:
    platform: Platform
    source_external_id: str
    source_name: str
    source_url: str
    post_external_id: str
    url: str
    text: str
    title: str | None
    published_at: datetime | None
    metrics: PostMetrics
    is_repost: bool
    repost_of_url: str | None
    fetched_at: datetime

    @property
    def key(self) -> tuple[Platform, str, str]:
        """Ключ уникальности публикации (ARCHITECTURE §5)."""
        return self.platform, self.source_external_id, self.post_external_id


@dataclass(frozen=True, slots=True)
class CollectResult:
    posts: list[RawPost]
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


class CollectorClient(Protocol):
    async def get_platforms(self, ctx: RequestContext) -> list[PlatformInfo]: ...

    async def resolve_source(self, ctx: RequestContext, url: str) -> SourceInfo: ...

    async def collect_from_source(
        self,
        ctx: RequestContext,
        platform: Platform,
        source_external_id: str,
        period: UtcPeriod,
        keywords: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult: ...

    async def search_platform(
        self,
        ctx: RequestContext,
        platform: Platform,
        queries: Sequence[str],
        period: UtcPeriod,
        region_terms: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult: ...

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceInfo:
    platform: str
    external_id: str
    screen_name: str
    url: str
    name: str
    city: str | None = None
    members_count: int | None = None
    is_closed: bool = False


@dataclass(frozen=True, slots=True)
class RawPost:
    platform: str
    source_external_id: str
    post_external_id: str
    url: str
    source_name: str
    source_url: str
    text: str
    title: str | None = None
    published_at: datetime | None = None
    metrics: dict[str, int] | None = None
    is_repost: bool = False
    repost_of_url: str | None = None


@dataclass(frozen=True, slots=True)
class CollectResult:
    posts: list[RawPost]
    truncated: bool = False
    warnings: Sequence[str] = ()


class CollectorClient(Protocol):
    async def resolve_source(self, url: str) -> SourceInfo: ...
    async def global_platforms(self) -> set[str]:
        """Площадки, которые сейчас умеют искать по всей площадке (GetPlatforms: global_mode)."""
        ...

    async def collect_from_source(
        self,
        *,
        platform: str,
        source_external_id: str,
        start_utc: datetime,
        end_utc: datetime,
        keywords: list[str],
        max_posts: int = 300,
    ) -> CollectResult: ...
    async def search_platform(
        self,
        *,
        platform: str,
        queries: list[str],
        start_utc: datetime,
        end_utc: datetime,
        region_terms: list[str],
        max_posts: int = 500,
    ) -> CollectResult: ...

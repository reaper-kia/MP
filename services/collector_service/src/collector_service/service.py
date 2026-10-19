"""Use-case слой: одинаковые гарантии для любой площадки, чтобы коннекторы не повторяли их.

- период: посты с датой вне периода отбрасываются, без даты — остаются (их пометит search);
- пустой текст: пост не возвращается, в warnings — сколько выкинули;
- дубли по (platform, source_external_id, post_external_id) внутри ответа схлопываются;
- max_posts: 0 → значение по умолчанию; лишнее обрезается, truncated=True.
"""

import logging
from collections.abc import Sequence

from collector_service.config import Settings
from collector_service.connectors.registry import ConnectorRegistry
from collector_service.errors import InvalidRequestError
from collector_service.models import CollectResult, Period, Platform, PlatformInfo, SourceInfo
from collector_service.urls import normalize_url

logger = logging.getLogger(__name__)


class CollectorService:
    def __init__(self, registry: ConnectorRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings

    async def get_platforms(self) -> list[PlatformInfo]:
        return [await connector.health() for connector in self._registry.all()]

    async def resolve_source(self, url: str) -> SourceInfo:
        normalized = normalize_url(url)
        connector = self._registry.detect(normalized)
        return await connector.resolve(normalized)

    async def collect_from_source(
        self,
        platform: Platform,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        if not source_external_id:
            raise InvalidRequestError("source_external_id обязателен")
        _check_period(period)
        limit = max_posts or self._settings.default_max_posts_source
        connector = self._registry.get(platform)
        result = await connector.collect(source_external_id, period, keywords, limit)
        return _finalize(result, period, limit, f"{platform}:{source_external_id}")

    async def search_platform(
        self,
        platform: Platform,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        cleaned = [q.strip() for q in queries if q.strip()]
        if not cleaned:
            raise InvalidRequestError("Нужна хотя бы одна поисковая фраза")
        _check_period(period)
        limit = max_posts or self._settings.default_max_posts_search
        connector = self._registry.get(platform)
        result = await connector.search(cleaned, period, region_terms, limit)
        return _finalize(result, period, limit, f"{platform}:search")


def _check_period(period: Period) -> None:
    if period.start > period.end:
        raise InvalidRequestError("Начало периода позже конца")


def _finalize(result: CollectResult, period: Period, limit: int, where: str) -> CollectResult:
    seen: set[tuple[Platform, str, str]] = set()
    posts = []
    empty = outside = 0
    for post in result.posts:
        if not post.text.strip():
            empty += 1
            continue
        if post.published_at is not None and not period.contains(post.published_at):
            outside += 1
            continue
        if post.key in seen:
            continue
        seen.add(post.key)
        posts.append(post)

    warnings = list(result.warnings)
    if empty:
        warnings.append(f"Пропущено постов без текста: {empty}")
    truncated = result.truncated or len(posts) > limit
    logger.info(
        "%s: got=%d kept=%d empty=%d outside_period=%d truncated=%s",
        where,
        len(result.posts),
        min(len(posts), limit),
        empty,
        outside,
        truncated,
    )
    return CollectResult(posts=posts[:limit], truncated=truncated, warnings=warnings)

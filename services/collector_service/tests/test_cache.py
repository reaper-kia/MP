"""Кэш сбора в Redis (B2-20): ключи, повтор без похода на площадку, что не кэшируется, fail-open."""

import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from collector_service.applications.context import RequestContext
from collector_service.applications.limits import CollectLimits
from collector_service.applications.mediator import Mediator
from collector_service.applications.queries.platforms import SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_mediator
from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import (
    CollectResult,
    Page,
    Period,
    PostMetrics,
    RawPost,
    SourceInfo,
)
from collector_service.infra.cache import TtlCache
from collector_service.infra.cache_codec import ZLIB_THRESHOLD, decode, encode
from collector_service.infra.connectors.fake import FakeConnector
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry
from collector_service.infra.redis_cache import RedisCache

CTX = RequestContext(request_id="t")
PERIOD = Period(
    start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)
OTHER_PERIOD = Period(start=PERIOD.start, end=datetime(2026, 10, 18, tzinfo=UTC))


class CountingFake(FakeConnector):
    """FakeConnector, который считает походы «на площадку»."""

    def __init__(self, platform: Platform, **kw: Any) -> None:
        super().__init__(platform, delay_seconds=0, **kw)
        self.collects = 0
        self.searches = 0

    def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        self.collects += 1
        return super().collect(source_external_id, period, keywords)

    def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        self.searches += 1
        return super().search(queries, period, region_terms)


def mediator_with(connector: FakeConnector, cache: Any, ttl: float = 600) -> Mediator:
    return build_mediator(
        InMemoryConnectorRegistry([connector]),
        CollectLimits(300, 500),
        cache,
        collect_cache_ttl=ttl,
    )


def collect(source: str = "krsk", period: Period = PERIOD, **kw: Any) -> CollectFromSourceQuery:
    return CollectFromSourceQuery(
        ctx=CTX, platform=Platform.VK, source_external_id=source, period=period, **kw
    )


# ---------- ключи ----------


def test_collect_key_has_platform_source_period_limit_but_not_keywords() -> None:
    key = collect(keywords=["дтп"]).cache_key()
    assert key == collect(keywords=["пожар"]).cache_key()  # фразы коннекторы не используют
    assert key == "mp:collect:v1:vk:krsk:2026-10-01T00:00:00Z-2026-10-19T23:59:00Z:0"
    assert key != collect(period=OTHER_PERIOD).cache_key()
    assert key != collect(source="other").cache_key()
    assert key != collect(max_posts=50).cache_key()


def test_platform_search_key_ignores_phrase_order_and_case_and_hides_text() -> None:
    def q(*phrases: str, period: Period = PERIOD) -> str | None:
        return SearchPlatformQuery(
            ctx=CTX, platform=Platform.OK, queries=list(phrases), period=period
        ).cache_key()

    key = q("ДТП Красноярск", "авария")
    assert key is not None and key.startswith("mp:psearch:v1:ok:")
    assert "дтп" not in key.lower()
    assert key == q("авария", "  дтп красноярск ")
    assert key != q("авария")
    assert key != q("ДТП Красноярск", "авария", period=OTHER_PERIOD)
    assert q("  ") is None


# ---------- поведение ----------


async def test_second_collect_comes_from_cache(caplog: pytest.LogCaptureFixture) -> None:
    fake = CountingFake(Platform.VK)
    mediator = mediator_with(fake, TtlCache())
    with caplog.at_level(logging.INFO, logger="collector_service.cache"):
        first = await mediator.send(collect())
        again = await mediator.send(collect(keywords=["другая тема"]))
    assert fake.collects == 1
    assert again.posts == first.posts
    messages = [r.getMessage() for r in caplog.records if r.name == "collector_service.cache"]
    assert any(m.startswith("cache miss key=mp:collect:v1:vk:krsk:") for m in messages)
    assert any(m.startswith("cache store key=mp:collect:v1:vk:krsk:") for m in messages)
    assert any(m.startswith("cache hit key=mp:collect:v1:vk:krsk:") for m in messages)

    await mediator.send(collect(period=OTHER_PERIOD))  # другой период — снова на площадку
    assert fake.collects == 2


async def test_platform_search_is_cached_too() -> None:
    fake = CountingFake(Platform.OK)
    mediator = mediator_with(fake, TtlCache())
    query = SearchPlatformQuery(ctx=CTX, platform=Platform.OK, queries=["дтп"], period=PERIOD)
    await mediator.send(query)
    await mediator.send(replace(query, queries=[" ДТП "]))
    assert fake.searches == 1


async def test_connector_error_is_not_cached() -> None:
    fake = CountingFake(Platform.VK)
    mediator = mediator_with(fake, TtlCache())
    for _ in range(2):
        with pytest.raises(Exception, match="тестовая ошибка"):
            await mediator.send(collect(source="fail"))
    assert fake.collects == 2


async def test_incomplete_collect_is_not_cached() -> None:
    """Бюджет времени кончился → ответ отдан, но в кэш не попал."""

    class SlowSecondPage(CountingFake):
        async def _pages(self) -> AsyncIterator[Page]:
            yield Page(posts=[])
            import asyncio

            await asyncio.sleep(1)
            yield Page(posts=[])

        def collect(
            self, source_external_id: str, period: Period, keywords: Sequence[str]
        ) -> AsyncIterator[Page]:
            self.collects += 1
            return self._pages()

    fake = SlowSecondPage(Platform.VK)
    mediator = build_mediator(
        InMemoryConnectorRegistry([fake]),
        CollectLimits(300, 500, budget_seconds=0.05),
        TtlCache(),
        collect_cache_ttl=600,
    )
    first = await mediator.send(collect())
    assert first.truncated and not first.complete
    await mediator.send(collect())
    assert fake.collects == 2


async def test_zero_ttl_disables_collect_cache_but_keeps_resolve() -> None:
    """CACHE_ENABLED=false: сбор как до B2-20, карточка источника — в памяти."""
    fake = CountingFake(Platform.VK)
    mediator = mediator_with(fake, TtlCache(), ttl=0)
    await mediator.send(collect())
    await mediator.send(collect())
    assert fake.collects == 2
    a = await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/krsk"))
    b = await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/krsk"))
    assert a == b


# ---------- Redis: кодек и fail-open ----------


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttl: dict[str, int | None] = {}

    async def get(self, name: str) -> bytes | None:
        return self.data.get(name)

    async def set(self, name: str, value: bytes, *, px: int | None = None) -> bool:
        self.data[name], self.ttl[name] = value, px
        return True


class BrokenRedis:
    async def get(self, name: str) -> bytes | None:
        raise ConnectionError("redis down")

    async def set(self, name: str, value: bytes, *, px: int | None = None) -> bool:
        raise ConnectionError("redis down")


def raw_post(i: int, text: str = "текст") -> RawPost:
    return RawPost(
        platform=Platform.VK,
        source_external_id="-1",
        source_name="Новости",
        source_url="https://vk.com/club1",
        post_external_id=str(i),
        url=f"https://vk.com/wall-1_{i}",
        text=text,
        title=None,
        published_at=PERIOD.start,
        metrics=PostMetrics(views=10, likes=None, reposts=1, comments=0),
        is_repost=i % 2 == 0,
        repost_of_url=None,
    )


def test_codec_roundtrip_and_zlib_for_big_values() -> None:
    small = CollectResult(posts=[raw_post(1), raw_post(2)], truncated=True, warnings=["w"])
    assert decode(encode(small)) == small
    assert encode(small)[:1] == b"j"

    big = CollectResult(posts=[raw_post(i, "длинный текст " * 50) for i in range(200)])
    data = encode(big)
    assert data[:1] == b"z" and len(data) < ZLIB_THRESHOLD
    assert decode(data) == big

    info = SourceInfo(Platform.OK, "123", "krsk", "https://ok.ru/krsk", "Красноярск", city=None)
    assert decode(encode(info)) == info


async def test_redis_cache_roundtrip_with_ttl() -> None:
    redis = FakeRedis()
    cache = RedisCache(redis)
    result = CollectResult(posts=[raw_post(1)])
    await cache.set("k", result, 600)
    assert redis.ttl["k"] == 600_000
    assert await cache.get("k") == result
    assert await cache.get("missing") is None


async def test_redis_down_means_miss_and_warning(caplog: pytest.LogCaptureFixture) -> None:
    fake = CountingFake(Platform.VK)
    mediator = mediator_with(fake, RedisCache(BrokenRedis()))
    with caplog.at_level(logging.WARNING):
        first = await mediator.send(collect())
        await mediator.send(collect())
    assert first.posts and fake.collects == 2  # сбор работает, просто без кэша
    assert any("cache unavailable" in r.getMessage() for r in caplog.records)


async def test_unreadable_record_is_a_miss() -> None:
    redis = FakeRedis()
    redis.data["k"] = b"\x80garbage"
    assert await RedisCache(redis).get("k") is None

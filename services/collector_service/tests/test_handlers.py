"""Гарантии хэндлеров на тестовой площадке — через Mediator, без сети и без proto."""

from datetime import UTC, datetime

import pytest

from collector_service.applications.context import RequestContext
from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.limits import CollectLimits
from collector_service.applications.mediator import Mediator
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_mediator
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    SourcePrivateError,
    UnsupportedUrlError,
)
from collector_service.domain.value_objects import CollectResult, Period
from collector_service.infra.connectors.fake import FakeConnector
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry

CTX = RequestContext(request_id="test")
LIMITS = CollectLimits(per_source=300, per_search=500)
PERIOD = Period(
    start=datetime(2026, 10, 1, tzinfo=UTC),
    end=datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC),
)


@pytest.fixture
def mediator() -> Mediator:
    registry = InMemoryConnectorRegistry(FakeConnector(p, delay_seconds=0) for p in Platform)
    return build_mediator(registry, LIMITS)


async def collect(
    mediator: Mediator,
    platform: Platform,
    source: str,
    period: Period = PERIOD,
    max_posts: int = 0,
) -> CollectResult:
    return await mediator.send(
        CollectFromSourceQuery(
            ctx=CTX,
            platform=platform,
            source_external_id=source,
            period=period,
            max_posts=max_posts,
        )
    )


async def test_resolve_detects_platform(mediator: Mediator) -> None:
    source = await mediator.send(ResolveSourceQuery(ctx=CTX, url="m.vk.com/krsk_news"))
    assert source.platform is Platform.VK and source.external_id == "krsk_news"
    ok = await mediator.send(ResolveSourceQuery(ctx=CTX, url="ok.ru/group/123"))
    assert ok.platform is Platform.OK
    with pytest.raises(UnsupportedUrlError):
        await mediator.send(ResolveSourceQuery(ctx=CTX, url="https://example.org/page"))
    with pytest.raises(SourcePrivateError):
        await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/closed"))


async def test_collect_respects_period_and_keeps_unknown_dates(mediator: Mediator) -> None:
    result = await collect(mediator, Platform.VK, "krsk_news")
    ids = {p.post_external_id for p in result.posts}
    assert "old" not in ids  # вне периода — отброшен
    assert any(p.published_at == PERIOD.start for p in result.posts)  # граница включительно
    assert any(p.published_at is None for p in result.posts)  # без даты — оставлен


async def test_collect_is_deterministic(mediator: Mediator) -> None:
    a = await collect(mediator, Platform.OK, "g1")
    b = await collect(mediator, Platform.OK, "g1")
    assert [p.key for p in a.posts] == [p.key for p in b.posts]


async def test_max_posts_truncates(mediator: Mediator) -> None:
    result = await collect(mediator, Platform.VK, "krsk_news", max_posts=2)
    assert len(result.posts) == 2 and result.truncated


async def test_errors(mediator: Mediator) -> None:
    with pytest.raises(PlatformUnavailableError):
        await collect(mediator, Platform.VK, "fail")
    empty = await collect(mediator, Platform.VK, "empty")
    assert empty.posts == []
    with pytest.raises(InvalidRequestError):
        await mediator.send(
            SearchPlatformQuery(ctx=CTX, platform=Platform.VK, queries=["  "], period=PERIOD)
        )
    bad = Period(start=PERIOD.end, end=PERIOD.start)
    with pytest.raises(InvalidRequestError):
        await collect(mediator, Platform.VK, "x", period=bad)
    with pytest.raises(InvalidRequestError):
        await collect(mediator, Platform.VK, "")


async def test_search_dedups_within_response(mediator: Mediator) -> None:
    result = await mediator.send(
        SearchPlatformQuery(
            ctx=CTX,
            platform=Platform.VK,
            queries=["ДТП"],
            period=PERIOD,
            region_terms=["Красноярск"],
        )
    )
    keys = [p.key for p in result.posts]
    assert len(keys) == len(set(keys)) and keys


async def test_platforms(mediator: Mediator) -> None:
    platforms = await mediator.send(GetPlatformsQuery(ctx=CTX))
    assert {p.platform for p in platforms} == set(Platform)
    assert all("ТЕСТОВЫЕ" in p.note for p in platforms)


async def test_every_query_has_a_handler() -> None:
    """Как test_uow в search_service: новый запрос без регистрации в build_mediator ловится сразу.

    Реестр пустой, поэтому каждый хэндлер доходит до своей «домашней» ошибки, а не до LookupError.
    """
    mediator = build_mediator(InMemoryConnectorRegistry([]), LIMITS)
    assert await mediator.send(GetPlatformsQuery(ctx=CTX)) == []
    with pytest.raises(UnsupportedUrlError):
        await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/krsk_news"))
    with pytest.raises(InvalidRequestError):
        await collect(mediator, Platform.VK, "krsk_news")
    with pytest.raises(InvalidRequestError):
        await mediator.send(
            SearchPlatformQuery(ctx=CTX, platform=Platform.VK, queries=["ДТП"], period=PERIOD)
        )

"""Гарантии CollectorService на тестовой площадке — без сети и без proto."""

from datetime import UTC, datetime

import pytest

from collector_service.config import Settings
from collector_service.connectors.fake import FakeConnector
from collector_service.connectors.registry import ConnectorRegistry
from collector_service.errors import (
    InvalidRequestError,
    PlatformUnavailableError,
    SourcePrivateError,
    UnsupportedUrlError,
)
from collector_service.models import Period, Platform
from collector_service.service import CollectorService
from collector_service.urls import normalize_url

PERIOD = Period(
    start=datetime(2026, 10, 1, tzinfo=UTC),
    end=datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC),
)


@pytest.fixture
def service() -> CollectorService:
    registry = ConnectorRegistry(FakeConnector(p, delay_seconds=0) for p in Platform)
    return CollectorService(registry, Settings())


def test_normalize_url() -> None:
    assert normalize_url(" vk.com/krsk_news/ ") == "https://vk.com/krsk_news"
    assert normalize_url("https://www.ok.ru/group/123?x=1#y") == "https://ok.ru/group/123"
    with pytest.raises(UnsupportedUrlError):
        normalize_url("   ")


async def test_resolve_detects_platform(service: CollectorService) -> None:
    source = await service.resolve_source("m.vk.com/krsk_news")
    assert source.platform is Platform.VK and source.external_id == "krsk_news"
    assert (await service.resolve_source("ok.ru/group/123")).platform is Platform.OK
    with pytest.raises(UnsupportedUrlError):
        await service.resolve_source("https://example.org/page")
    with pytest.raises(SourcePrivateError):
        await service.resolve_source("vk.com/closed")


async def test_collect_respects_period_and_keeps_unknown_dates(service: CollectorService) -> None:
    result = await service.collect_from_source(Platform.VK, "krsk_news", PERIOD, [], 0)
    ids = {p.post_external_id for p in result.posts}
    assert "old" not in ids  # вне периода — отброшен
    assert any(p.published_at == PERIOD.start for p in result.posts)  # граница включительно
    assert any(p.published_at is None for p in result.posts)  # без даты — оставлен


async def test_collect_is_deterministic(service: CollectorService) -> None:
    a = await service.collect_from_source(Platform.OK, "g1", PERIOD, [], 0)
    b = await service.collect_from_source(Platform.OK, "g1", PERIOD, [], 0)
    assert [p.key for p in a.posts] == [p.key for p in b.posts]


async def test_max_posts_truncates(service: CollectorService) -> None:
    result = await service.collect_from_source(Platform.VK, "krsk_news", PERIOD, [], 2)
    assert len(result.posts) == 2 and result.truncated


async def test_errors(service: CollectorService) -> None:
    with pytest.raises(PlatformUnavailableError):
        await service.collect_from_source(Platform.VK, "fail", PERIOD, [], 0)
    empty = await service.collect_from_source(Platform.VK, "empty", PERIOD, [], 0)
    assert empty.posts == []
    with pytest.raises(InvalidRequestError):
        await service.search_platform(Platform.VK, ["  "], PERIOD, [], 0)
    bad = Period(start=PERIOD.end, end=PERIOD.start)
    with pytest.raises(InvalidRequestError):
        await service.collect_from_source(Platform.VK, "x", bad, [], 0)


async def test_search_dedups_within_response(service: CollectorService) -> None:
    result = await service.search_platform(Platform.VK, ["ДТП"], PERIOD, ["Красноярск"], 0)
    keys = [p.key for p in result.posts]
    assert len(keys) == len(set(keys)) and keys


async def test_platforms(service: CollectorService) -> None:
    platforms = await service.get_platforms()
    assert {p.platform for p in platforms} == set(Platform)
    assert all("ТЕСТОВЫЕ" in p.note for p in platforms)

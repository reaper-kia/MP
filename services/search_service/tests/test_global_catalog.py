"""Режим «везде»: все активные источники каталога + поиск по всей площадке, где он есть."""

import pytest

from search_service.applications.handlers.searches import (
    NO_GLOBAL_TARGETS,
    SearchHandler,
    StartSearchRequest,
)
from search_service.domain.enums import SearchMode, TargetKind
from search_service.domain.errors import SearchInvalidParams
from tests.builders import add_source
from tests.fakes import FakeCollector, FakeRunner, InMemoryUoW


def global_request(*platforms: str) -> StartSearchRequest:
    return StartSearchRequest(
        query="ДТП на трассе",
        period_from="2026-10-13",
        period_to="2026-10-20",
        mode=SearchMode.GLOBAL,
        platforms=list(platforms),
        source_ids=[],
    )


async def test_global_search_reads_all_active_catalog_sources() -> None:
    uow = InMemoryUoW()
    regional = await add_source(uow, "krsk")
    federal = await add_source(uow, "moscow", is_regional=False)  # край проверит оценка по тексту
    paused = await add_source(uow, "paused")
    paused.is_active = False
    ok = await add_source(uow, "okgroup")
    ok.platform = "ok"

    runner = FakeRunner()
    search = await SearchHandler(uow, runner).start(global_request("vk"))
    kinds = [(t.kind, t.platform, t.source_id) for t in search.targets]
    assert kinds == [
        (TargetKind.PLATFORM_SEARCH, "vk", None),
        (TargetKind.SOURCE, "vk", regional.id),
        (TargetKind.SOURCE, "vk", federal.id),
    ]
    assert runner.launched == [search.id]


async def test_no_platform_search_where_collector_cannot_search() -> None:
    """VK без ключа Яндекса: цели «поиск по всей площадке» нет — не падает зря, только каталог."""
    uow = InMemoryUoW()
    krsk = await add_source(uow, "krsk")
    collector = FakeCollector()
    collector.no_global = {"vk", "ok", "max"}

    search = await SearchHandler(uow, FakeRunner(), collector).start(global_request("vk", "news"))
    kinds = [(t.kind, t.platform, t.source_id) for t in search.targets]
    assert kinds == [
        (TargetKind.PLATFORM_SEARCH, "news", None),
        (TargetKind.SOURCE, "vk", krsk.id),
    ]


async def test_collector_without_platforms_answer_means_catalog_only() -> None:
    uow = InMemoryUoW()
    krsk = await add_source(uow, "krsk")
    collector = FakeCollector()
    collector.platforms_down = True

    search = await SearchHandler(uow, FakeRunner(), collector).start(global_request("vk"))
    assert [(t.kind, t.source_id) for t in search.targets] == [(TargetKind.SOURCE, krsk.id)]


async def test_nothing_to_search_is_a_clear_error() -> None:
    uow = InMemoryUoW()
    collector = FakeCollector()
    collector.no_global = {"vk"}
    runner = FakeRunner()

    with pytest.raises(SearchInvalidParams) as info:
        await SearchHandler(uow, runner, collector).start(global_request("vk"))
    assert NO_GLOBAL_TARGETS in str(info.value) and runner.launched == []

"""Режим «везде»: поиск площадки + стены активных региональных источников каталога."""

from search_service.applications.handlers.searches import SearchHandler, StartSearchRequest
from search_service.domain.enums import SearchMode, TargetKind
from tests.builders import add_source
from tests.fakes import FakeRunner, InMemoryUoW


async def test_global_search_also_reads_catalog_sources() -> None:
    uow = InMemoryUoW()
    regional = await add_source(uow, "krsk")
    await add_source(uow, "moscow", is_regional=False)
    paused = await add_source(uow, "paused")
    paused.is_active = False
    ok = await add_source(uow, "okgroup")
    ok.platform = "ok"

    runner = FakeRunner()
    search = await SearchHandler(uow, runner).start(
        StartSearchRequest(
            query="ДТП на трассе",
            period_from="2026-10-13",
            period_to="2026-10-20",
            mode=SearchMode.GLOBAL,
            platforms=["vk"],
            source_ids=[],
        )
    )
    kinds = [(t.kind, t.platform, t.source_id) for t in search.targets]
    assert kinds == [
        (TargetKind.PLATFORM_SEARCH, "vk", None),
        (TargetKind.SOURCE, "vk", regional.id),
    ]
    assert runner.launched == [search.id]

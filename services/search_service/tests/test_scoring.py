"""ScoringHandler: «в подборке» у цели (B2-07), регион в «везде» (B2-06), нарезка GroupPosts."""

import pytest

from search_service.applications.handlers.control import ControlHandler
from search_service.applications.handlers.scoring import (
    GROUP_POSTS_LIMIT,
    NO_REGION_EXPLANATION,
    ScoringHandler,
)
from search_service.applications.ports.ml_client import QueryAnalysis
from search_service.domain.enums import QueryType, Relevance, SearchMode
from tests.builders import add_result, add_search, add_source
from tests.fakes import FakeMl, FakeRunner, InMemoryUoW

ANALYSIS = QueryAnalysis(QueryType.TOPIC.value, "Безопасность на дорогах", ["дороги"])


@pytest.fixture
def uow() -> InMemoryUoW:
    return InMemoryUoW()


@pytest.fixture
def ml() -> FakeMl:
    return FakeMl()


async def test_matched_counts_only_posts_in_selection(uow, ml):
    """B2-07 DoD: цель с 3 постами, один IRRELEVANT → matched == 2."""
    source = await add_source(uow, "s1")
    search = await add_search(uow, [source])
    target = search.targets[0]
    results = [
        await add_result(uow, search, target, 1, "ДТП на трассе"),
        await add_result(uow, search, target, 2, "Ремонт дороги"),
        await add_result(uow, search, target, 3, "Концерт в парке"),
    ]
    ml.relevance_by_text = {"Концерт": Relevance.IRRELEVANT}

    await ScoringHandler(uow, ml).score_results(search.id, [r.id for r in results])

    assert target.matched == 2


async def test_matched_drops_when_result_excluded_manually(uow, ml):
    source = await add_source(uow, "s1")
    search = await add_search(uow, [source])
    target = search.targets[0]
    results = [await add_result(uow, search, target, n, f"Пост {n}") for n in (1, 2, 3)]
    await ScoringHandler(uow, ml).score_results(search.id, [r.id for r in results])
    assert target.matched == 3

    control = ControlHandler(uow, FakeRunner())
    counts = await control.set_excluded(search.id, [results[0].id], True)
    assert counts["total"] == 2
    assert target.matched == 2

    await control.set_excluded(search.id, [results[0].id], False)
    assert target.matched == 3


async def test_matched_is_counted_per_target(uow, ml):
    a, b = await add_source(uow, "a"), await add_source(uow, "b")
    search = await add_search(uow, [a, b])
    ta, tb = search.targets
    ra = [await add_result(uow, search, ta, n, f"A{n}", source="a") for n in (1, 2)]
    rb = [await add_result(uow, search, tb, n, f"Концерт {n}", source="b") for n in (1, 2, 3)]
    ml.relevance_by_text = {"Концерт": Relevance.IRRELEVANT}

    await ScoringHandler(uow, ml).score_search(search.id, ANALYSIS)

    assert (ta.matched, tb.matched) == (len(ra), 0)
    assert len(rb) == 3


async def test_global_mode_drops_posts_without_region(uow, ml):
    """B2-06 п.1: «везде», источник не региональный и в тексте края нет → IRRELEVANT."""
    source = await add_source(uow, "fed", is_regional=False)
    search = await add_search(uow, [source], mode=SearchMode.GLOBAL)
    target = search.targets[0]
    no_region = await add_result(uow, search, target, 1, "Новости страны", region_by_source=False)
    in_text = await add_result(
        uow, search, target, 2, "Авария в Красноярске", region_by_source=False
    )
    by_source = await add_result(uow, search, target, 3, "Общая новость", region_by_source=True)
    ml.region_texts = {"Красноярск"}

    await ScoringHandler(uow, ml).score_search(search.id, ANALYSIS)

    assert no_region.relevance is Relevance.IRRELEVANT
    assert no_region.explanation == NO_REGION_EXPLANATION
    assert in_text.relevance is Relevance.DIRECT
    assert in_text.region_by_content is True
    assert by_source.relevance is Relevance.DIRECT
    assert target.matched == 2


async def test_selected_mode_does_not_apply_region_rule(uow, ml):
    source = await add_source(uow, "any", is_regional=False)
    search = await add_search(uow, [source], mode=SearchMode.SELECTED)
    result = await add_result(
        uow, search, search.targets[0], 1, "Новости страны", region_by_source=False
    )

    await ScoringHandler(uow, ml).score_search(search.id, ANALYSIS)

    assert result.relevance is Relevance.DIRECT


async def test_ml_failure_keeps_posts_disputed_even_in_global_mode(uow, ml):
    """Если ML недоступен, регион неизвестен: пост остаётся «спорным», а не «не связан»."""
    source = await add_source(uow, "fed", is_regional=False)
    search = await add_search(uow, [source], mode=SearchMode.GLOBAL)
    result = await add_result(uow, search, search.targets[0], 1, "Новости", region_by_source=False)
    ml.unavailable = True

    await ScoringHandler(uow, ml).score_search(search.id, ANALYSIS)

    assert result.relevance is Relevance.DISPUTED


async def test_group_posts_is_split_by_ml_limit(uow, ml):
    """B2-06 п.2: ml.GroupPosts принимает до 500 постов — режем и не склеиваем id групп."""
    source = await add_source(uow, "s1")
    search = await add_search(uow, [source])
    target = search.targets[0]
    total = GROUP_POSTS_LIMIT * 2 + 100
    for n in range(total):
        await add_result(uow, search, target, n, f"Пост {n}")
    handler = ScoringHandler(uow, ml)
    await handler.score_search(search.id, ANALYSIS)

    await handler.group_search(search.id)

    assert ml.group_calls == [GROUP_POSTS_LIMIT, GROUP_POSTS_LIMIT, 100]
    group_ids = [r.group_id for r in await uow.results.get_by_search(search.id)]
    assert all(group_ids)
    # FakeMl кладёт каждый пост в свою группу g1..gN в каждом вызове — id не должны совпасть
    assert len(set(group_ids)) == total


async def test_group_posts_failed_chunk_does_not_stop_others(uow, ml):
    source = await add_source(uow, "s1")
    search = await add_search(uow, [source])
    for n in range(GROUP_POSTS_LIMIT + 5):
        await add_result(uow, search, search.targets[0], n, f"Пост {n}")
    handler = ScoringHandler(uow, ml)
    await handler.score_search(search.id, ANALYSIS)

    calls = 0
    original = ml.group_posts

    async def flaky(posts):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("ml упал")
        return await original(posts)

    ml.group_posts = flaky  # type: ignore[method-assign]
    await handler.group_search(search.id)

    grouped = [r for r in await uow.results.get_by_search(search.id) if r.group_id]
    assert len(grouped) == 5

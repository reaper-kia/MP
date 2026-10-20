"""Правила ТЗ, которые показываем на защите: названия тестов = формулировки проверок (B2-13)."""

import asyncio

import pytest

from search_service.applications.handlers.control import ControlHandler
from search_service.applications.handlers.pipeline import Pipeline
from search_service.applications.handlers.save import SaveHandler
from search_service.applications.handlers.scoring import ScoringHandler
from search_service.applications.handlers.views import result_view
from search_service.applications.ports.ml_client import QueryAnalysis
from search_service.domain.enums import QueryType, SearchStatus, TargetStatus
from tests.builders import add_result, add_search, add_source, raw_post
from tests.fakes import FakeCollector, FakeMl, FakeRunner, InMemoryUoW

ANALYSIS = QueryAnalysis(QueryType.TOPIC.value, "Безопасность на дорогах", ["дороги"])


@pytest.fixture
def uow() -> InMemoryUoW:
    return InMemoryUoW()


@pytest.fixture
def collector() -> FakeCollector:
    return FakeCollector()


@pytest.fixture
def ml() -> FakeMl:
    return FakeMl()


def pipeline(uow: InMemoryUoW, collector: FakeCollector, ml: FakeMl) -> Pipeline:
    return Pipeline(uow, collector, ml, asyncio.Semaphore(5), 10)


async def test_same_text_in_three_groups_is_three_records(uow):
    """Один текст, опубликованный в трёх группах, — три публикации и три строки подборки."""
    sources = [await add_source(uow, name) for name in ("a", "b", "c")]
    search = await add_search(uow, sources)
    text = "Одинаковый текст про безопасность на дорогах"

    for source, target in zip(sources, search.targets, strict=True):
        await SaveHandler(uow).save_posts(
            search, target, [raw_post(1, text, source=source.external_id)]
        )

    results = await uow.results.get_by_search(search.id)
    assert len(results) == 3
    assert len({r.publication_id for r in results}) == 3
    assert len(uow.publications.store) == 3
    assert {p.text for p in uow.publications.store.values()} == {text}


@pytest.mark.parametrize(
    "span",
    [(0, 20), (4, 17), (0, 99999), (-3, 8), (10, 5), (7, 7), None],
    ids=["head", "middle", "past-end", "negative", "reversed", "empty", "default"],
)
async def test_excerpt_is_substring_of_original(uow, ml, span):
    """Выдержка — всегда кусок исходного текста; кривые позиции от ML не попадают в подборку."""
    source = await add_source(uow, "s1")
    search = await add_search(uow, [source])
    text = "Госавтоинспекция края: число ДТП с пострадавшими снизилось на треть за год."
    result = await add_result(uow, search, search.targets[0], 1, text)
    ml.excerpt_span = span

    await ScoringHandler(uow, ml).score_search(search.id, ANALYSIS)

    (pub,) = uow.publications.store.values()
    assert result.excerpt_start is not None and result.excerpt_end is not None
    assert 0 <= result.excerpt_start < result.excerpt_end <= len(pub.text)
    excerpt = result_view(result, pub, None, 1).excerpt
    assert excerpt and excerpt in pub.text


async def test_retry_does_not_duplicate(uow, collector, ml):
    """Повтор упавшей цели: посты, которые уже есть в подборке, второй раз не добавляются."""
    a, b = await add_source(uow, "a"), await add_source(uow, "b")
    search = await add_search(uow, [a, b])
    collector.posts[("vk", "a")] = [raw_post(1, source="a"), raw_post(2, source="a")]
    collector.failing["b"] = "RATE_LIMITED"
    run = pipeline(uow, collector, ml)

    await run.run(search.id)
    assert search.status is SearchStatus.PARTIAL
    before = {r.publication_id for r in await uow.results.get_by_search(search.id)}
    assert len(before) == 2

    # источник b ожил и отдаёт 2 новых поста и один уже виденный (тот же пост из того же источника)
    collector.failing.clear()
    collector.posts[("vk", "b")] = [
        raw_post(10, source="b"),
        raw_post(11, source="b"),
        raw_post(10, source="b"),
    ]
    await ControlHandler(uow, FakeRunner()).retry(search.id, None)
    await run.run(search.id)
    # и ещё раз: повтор уже завершённого поиска без упавших целей ничего не добавляет
    await ControlHandler(uow, FakeRunner()).retry(search.id, None)

    results = await uow.results.get_by_search(search.id)
    assert search.status is SearchStatus.COMPLETED
    assert len(results) == 4
    assert len({r.publication_id for r in results}) == 4
    assert before <= {r.publication_id for r in results}
    assert (await uow.results.counts(search.id))["total"] == 4


async def test_pipeline_partial_when_one_of_three_targets_fails(uow, collector, ml):
    """3 цели, одна упала → PARTIAL; посты двух других сохранены и оценены."""
    sources = [await add_source(uow, name) for name in ("a", "b", "c")]
    search = await add_search(uow, sources)
    collector.posts[("vk", "a")] = [raw_post(1, source="a"), raw_post(2, source="a")]
    collector.posts[("vk", "c")] = [raw_post(3, source="c")]
    collector.failing["b"] = "RATE_LIMITED"

    await pipeline(uow, collector, ml).run(search.id)

    statuses = {t.name: t.status for t in search.targets}
    assert statuses == {
        "Источник a": TargetStatus.DONE,
        "Источник b": TargetStatus.FAILED,
        "Источник c": TargetStatus.DONE,
    }
    failed = next(t for t in search.targets if t.status is TargetStatus.FAILED)
    assert failed.error_code == "RATE_LIMITED" and failed.error_message
    assert search.status is SearchStatus.PARTIAL
    counts = await uow.results.counts(search.id)
    assert counts["total"] == 3
    assert [t.matched for t in search.targets] == [2, 0, 1]


async def test_pipeline_all_targets_empty_is_completed_with_zero_total(uow, collector, ml):
    """Пустой результат — не ошибка: COMPLETED, total=0, цели EMPTY."""
    sources = [await add_source(uow, name) for name in ("a", "b")]
    search = await add_search(uow, sources)

    await pipeline(uow, collector, ml).run(search.id)

    assert search.status is SearchStatus.COMPLETED
    assert [t.status for t in search.targets] == [TargetStatus.EMPTY, TargetStatus.EMPTY]
    counts = await uow.results.counts(search.id)
    assert counts["total"] == 0 and counts["rejected"] == 0


async def test_pipeline_all_targets_failed_is_failed(uow, collector, ml):
    sources = [await add_source(uow, name) for name in ("a", "b")]
    search = await add_search(uow, sources)
    collector.failing.update({"a": "PLATFORM_UNAVAILABLE", "b": "SOURCE_PRIVATE"})

    await pipeline(uow, collector, ml).run(search.id)

    assert search.status is SearchStatus.FAILED
    assert all(t.error_message for t in search.targets)


@pytest.mark.parametrize(
    ("show", "expected"), [(True, "ML работал в упрощённом режиме"), (False, None)]
)
async def test_degraded_warning_can_be_hidden(uow, collector, ml, show, expected):
    """ML-15: ML_SHOW_DEGRADED_WARNING=false — эвристики ML не показываем пользователю."""
    ml.degraded = True
    search = await add_search(uow, [await add_source(uow, "a")])
    runner = Pipeline(uow, collector, ml, asyncio.Semaphore(5), 10, show_degraded_warning=show)
    _, warning = await runner._analyze(search)
    assert warning == expected

    ml.degraded = False  # модель ответила (ноут или Яндекс) — предупреждения нет никогда
    _, warning = await runner._analyze(search)
    assert warning is None

"""B2-12: request_id запроса gateway доходит до collector и ml через фоновый пайплайн."""

import asyncio

from search_service.applications.handlers.pipeline import Pipeline
from search_service.applications.request_context import bind_request_id, current_request_id
from search_service.infra.runner import SearchRunner
from tests.builders import add_search, add_source, raw_post
from tests.fakes import FakeCollector, FakeMl, InMemoryUoW


async def run_search_as(runner: SearchRunner, uow: InMemoryUoW, request_id: str, source) -> None:
    """Как StartSearch: запрос выставил request_id и запустил пайплайн фоновой задачей."""

    async def handler() -> None:  # у каждого gRPC-вызова свой контекст (своя задача)
        bind_request_id(request_id)
        search = await add_search(uow, [source])
        await runner.launch(search.id)

    await asyncio.create_task(handler())
    for task in list(runner._tasks.values()):
        await task


async def test_request_id_reaches_collector_and_ml():
    uow, collector, ml = InMemoryUoW(), FakeCollector(), FakeMl()
    source = await add_source(uow, "s1")
    collector.posts[("vk", "s1")] = [raw_post(1, source="s1")]
    runner = SearchRunner(Pipeline(uow, collector, ml, asyncio.Semaphore(5), 10))

    await run_search_as(runner, uow, "req-111", source)
    await run_search_as(runner, uow, "req-222", source)

    assert collector.request_ids == ["req-111", "req-222"]
    assert ml.request_ids == ["req-111", "req-222"]
    assert current_request_id() == ""  # запросы не протекают друг в друга

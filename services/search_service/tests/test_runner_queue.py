"""Очередь поисков (B2-15): не больше max_parallel пайплайнов одновременно, отмена в очереди."""

import asyncio
import uuid

from search_service.infra.runner import SearchRunner


class GatedPipeline:
    """Пайплайн, который ждёт разрешения теста: видно, кто запущен, а кто стоит в очереди."""

    def __init__(self) -> None:
        self.started: list[uuid.UUID] = []
        self.release: dict[uuid.UUID, asyncio.Event] = {}

    async def run(self, search_id: uuid.UUID) -> None:
        self.started.append(search_id)
        await self.release.setdefault(search_id, asyncio.Event()).wait()

    def finish(self, search_id: uuid.UUID) -> None:
        self.release.setdefault(search_id, asyncio.Event()).set()


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_second_search_waits_for_the_first() -> None:
    pipeline = GatedPipeline()
    runner = SearchRunner(pipeline, max_parallel=1)  # type: ignore[arg-type]
    first, second = uuid.uuid4(), uuid.uuid4()

    await runner.launch(first)
    await runner.launch(second)
    await settle()
    assert pipeline.started == [first]  # второй — в очереди

    pipeline.finish(first)
    await settle()
    assert pipeline.started == [first, second]
    pipeline.finish(second)
    await settle()


async def test_parallel_limit_from_settings() -> None:
    pipeline = GatedPipeline()
    runner = SearchRunner(pipeline, max_parallel=2)  # type: ignore[arg-type]
    ids = [uuid.uuid4() for _ in range(3)]
    for i in ids:
        await runner.launch(i)
    await settle()
    assert pipeline.started == ids[:2]
    for i in ids:
        pipeline.finish(i)
    await settle()
    assert pipeline.started == ids


async def test_cancel_queued_search_never_runs() -> None:
    pipeline = GatedPipeline()
    runner = SearchRunner(pipeline, max_parallel=1)  # type: ignore[arg-type]
    first, queued = uuid.uuid4(), uuid.uuid4()
    await runner.launch(first)
    await runner.launch(queued)
    await settle()

    await runner.cancel(queued)
    pipeline.finish(first)
    await settle()
    assert pipeline.started == [first]

    third = uuid.uuid4()  # слот освободился — очередь не застряла
    await runner.launch(third)
    await settle()
    assert pipeline.started == [first, third]
    pipeline.finish(third)
    await settle()

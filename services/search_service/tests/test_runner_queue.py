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


class TwinPipeline(GatedPipeline):
    """Оригинал идёт «в другом процессе»: is_final из базы, adopt — копия готовой подборки."""

    def __init__(self, leader_ok: bool = True) -> None:
        super().__init__()
        self.final = False
        self.leader_ok = leader_ok
        self.adopted: list[uuid.UUID] = []
        self.forgotten: list[uuid.UUID] = []

    async def is_final(self, search_id: uuid.UUID) -> bool:
        return self.final

    async def adopt(self, search_id: uuid.UUID, leader_id: uuid.UUID) -> bool:
        if self.leader_ok:
            self.adopted.append(search_id)
        return self.leader_ok

    async def forget_twin(self, search_id: uuid.UUID) -> None:
        self.forgotten.append(search_id)


async def test_follower_polls_leader_from_other_process(monkeypatch) -> None:
    import search_service.infra.runner as runner_module

    monkeypatch.setattr(runner_module, "FOLLOW_POLL_SECONDS", 0.01)
    pipeline = TwinPipeline()
    runner = SearchRunner(pipeline, max_parallel=1)  # type: ignore[arg-type]
    leader, repeat = uuid.uuid4(), uuid.uuid4()
    await runner.follow(repeat, leader)
    await asyncio.sleep(0.05)
    assert pipeline.adopted == [] and pipeline.started == []
    pipeline.final = True
    await asyncio.sleep(0.05)
    assert pipeline.adopted == [repeat] and pipeline.started == []


async def test_follower_runs_itself_without_selection() -> None:
    pipeline = TwinPipeline(leader_ok=False)
    runner = SearchRunner(pipeline, max_parallel=1)  # type: ignore[arg-type]
    leader, repeat = uuid.uuid4(), uuid.uuid4()
    await runner.launch(leader)
    await runner.follow(repeat, leader)
    await settle()
    assert pipeline.started == [leader]  # повтор ждёт, слот не занимает
    pipeline.finish(leader)
    await settle()
    assert pipeline.forgotten == [repeat] and pipeline.started == [leader, repeat]
    pipeline.finish(repeat)
    await settle()

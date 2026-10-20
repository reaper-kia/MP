"""Тесты глобальной очередности поисков (B2-15)."""
import pytest
import asyncio
import uuid
from datetime import date, timedelta

from search_service.domain.entities import Search, SearchTarget
from search_service.domain.value_objects import Period
from search_service.infra.runner import SearchRunner
import search_service.infra.runner as runner_module 
from tests.fakes import InMemoryUoW


class ControllableFakePipeline:
    """Фейковый пайплайн, которым можно управлять из теста."""
    def __init__(self):
        self.started_event = asyncio.Event()
        self.finish_event = asyncio.Event()
        self.executed_searches = []

    async def run(self, search_id: uuid.UUID):
        self.executed_searches.append(search_id)
        self.started_event.set()  # Сообщаем тесту, что пайплайн начался
        await self.finish_event.wait()  # Ждём, пока тест не разрешит завершиться


@pytest.fixture
def uow():
    return InMemoryUoW()


@pytest.fixture
def pipeline():
    return ControllableFakePipeline()


@pytest.fixture
def runner(pipeline):
    runner_module.GLOBAL_PIPELINE_SEMAPHORE = asyncio.Semaphore(1)
    return SearchRunner(pipeline)


@pytest.mark.asyncio
async def test_second_search_waits_in_queue(uow, pipeline, runner):
    """
    DoD B2-15: Два поиска подряд — второй остаётся в очереди, пока первый не завершится.
    """
    search1 = Search(query="q1", period=Period(date.today(), date.today() + timedelta(days=1)), mode="selected")
    search1.targets = [SearchTarget(kind="source", platform="vk", name="t1")]
    
    search2 = Search(query="q2", period=Period(date.today(), date.today() + timedelta(days=1)), mode="selected")
    search2.targets = [SearchTarget(kind="source", platform="vk", name="t2")]

    async with uow:
        await uow.searches.add(search1)
        await uow.searches.add(search2)
        await uow.commit()

    # Запускаем первый поиск
    task1 = asyncio.create_task(runner.launch(search1.id))
    
    # Ждём, пока первый поиск захватит семафор и начнёт выполняться
    await asyncio.wait_for(pipeline.started_event.wait(), timeout=2.0)
    
    # Сбрасываем событие для второго поиска
    pipeline.started_event.clear()
    # ВАЖНО: сбрасываем finish_event, чтобы второй поиск не завершился мгновенно
    pipeline.finish_event.clear()
    
    # Запускаем второй поиск
    task2 = asyncio.create_task(runner.launch(search2.id))
    
    # Даём событиям обработаться
    await asyncio.sleep(0.1)
    
    # Проверяем: второй поиск всё ещё в очереди
    assert len(pipeline.executed_searches) == 1, "Второй поиск не должен был начать выполняться"
    assert pipeline.executed_searches[0] == search1.id

    # Разрешаем первому поиску завершиться
    pipeline.finish_event.set()
    await task1
    
    # ДАЁМ EVENT LOOP ВОЗМОЖНОСТЬ ПЕРЕКЛЮЧИТЬСЯ НА ВТОРОЙ ПОИСК
    await asyncio.sleep(0.1)
    
    # Теперь ждём завершения второго поиска
    await asyncio.wait_for(task2, timeout=2.0)
    
    # Проверяем, что оба поиска выполнились
    assert len(pipeline.executed_searches) == 2, f"Ожидалось 2 выполнения, получено {len(pipeline.executed_searches)}"
    assert search2.id in pipeline.executed_searches

@pytest.mark.asyncio
async def test_cancel_queued_search(uow, pipeline, runner):
    """
    DoD B2-15: Отмена поиска, который стоит в очереди, работает корректно.
    """
    search1 = Search(query="q1", period=Period(date.today(), date.today() + timedelta(days=1)), mode="selected")
    search1.targets = [SearchTarget(kind="source", platform="vk", name="t1")]
    
    search2 = Search(query="q2", period=Period(date.today(), date.today() + timedelta(days=1)), mode="selected")
    search2.targets = [SearchTarget(kind="source", platform="vk", name="t2")]

    async with uow:
        await uow.searches.add(search1)
        await uow.searches.add(search2)
        await uow.commit()

    # Запускаем первый, он занимает слот
    task1 = asyncio.create_task(runner.launch(search1.id))
    await asyncio.wait_for(pipeline.started_event.wait(), timeout=2.0)

    # Запускаем второй и сразу отменяем его
    task2 = asyncio.create_task(runner.launch(search2.id))
    await runner.cancel(search2.id)
    
    # Разрешаем первому завершиться
    pipeline.finish_event.set()
    await task1
    
    # Второй поиск не должен был выполниться
    assert len(pipeline.executed_searches) == 1
    assert search2.id not in pipeline.executed_searches
"""Поток страниц коннектора → CollectResult тем же путём, что в сервисе (drain)."""

from collections.abc import AsyncIterator

from collector_service.applications.budget import Budget
from collector_service.applications.collecting import drain
from collector_service.domain.services import PostAccumulator
from collector_service.domain.value_objects import CollectResult, Page, Period


async def gather(
    pages: AsyncIterator[Page], period: Period, limit: int, budget_seconds: float = 60.0
) -> CollectResult:
    acc = PostAccumulator(period, limit)
    await drain(pages, acc, Budget.start(budget_seconds, None))
    result, _ = acc.result()
    return result

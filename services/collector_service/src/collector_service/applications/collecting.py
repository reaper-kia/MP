"""Как потребляется поток страниц от коннектора: лимит постов, бюджет времени, частичный ответ.

Здесь, а не в коннекторах, потому что правило одно на все площадки:
- набрали max_posts → дальше площадку не дёргаем, truncated=True;
- кончился бюджет времени → отдаём то, что успели, truncated=True и предупреждение (B1-09 п. 2);
- площадка упала на первой же странице → ошибка наверх (search_service покажет причину);
  упала позже → отдаём уже полученное, truncated=True и предупреждение с причиной.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from collector_service.applications.budget import Budget
from collector_service.domain.exceptions import CollectorError
from collector_service.domain.services import PostAccumulator
from collector_service.domain.value_objects import Page


def time_warning(budget: Budget) -> str:
    return (
        f"Сбор остановлен по времени ({budget.seconds:.0f} с): "
        "отданы публикации, полученные до остановки"
    )


async def drain(pages: AsyncIterator[Page], acc: PostAccumulator, budget: Budget) -> None:
    received_pages = 0
    try:
        while not acc.truncated:
            remaining = budget.remaining()
            if remaining <= 0:
                acc.truncated = True
                acc.warn(time_warning(budget))
                return
            try:
                async with asyncio.timeout(remaining):
                    page = await anext(pages)
            except StopAsyncIteration:
                return
            except TimeoutError:
                acc.truncated = True
                acc.warn(time_warning(budget))
                return
            except CollectorError as exc:
                if received_pages == 0:
                    raise
                acc.truncated = True
                acc.warn(f"Сбор прерван: {exc}. Отданы публикации, полученные до ошибки")
                return
            received_pages += 1
            acc.add(page.posts)
            for warning in page.warnings:
                acc.warn(warning)
            acc.truncated |= page.truncated
    finally:
        aclose = getattr(pages, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()

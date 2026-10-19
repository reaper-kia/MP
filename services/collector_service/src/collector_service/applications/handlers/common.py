"""Общее для хэндлеров сбора постов."""

import logging
from collections.abc import AsyncIterator

from collector_service.applications.budget import Budget
from collector_service.applications.collecting import drain
from collector_service.applications.context import RequestContext
from collector_service.applications.exceptions import InvalidRequestError
from collector_service.domain.services import FinalizeStats, PostAccumulator
from collector_service.domain.value_objects import CollectResult, Page, Period

logger = logging.getLogger(__name__)


def check_period(period: Period) -> None:
    if period.start > period.end:
        raise InvalidRequestError("Начало периода позже конца")


async def collect_pages(
    ctx: RequestContext,
    where: str,
    pages: AsyncIterator[Page],
    period: Period,
    limit: int,
    budget_seconds: float,
) -> CollectResult:
    """Поток страниц → ответ: общие гарантии, лимит, бюджет времени, строка в лог."""
    acc = PostAccumulator(period, limit)
    budget = Budget.start(budget_seconds, ctx.time_remaining)
    await drain(pages, acc, budget)
    result, stats = acc.result()
    log_finalized(ctx, where, stats, result.truncated, budget)
    return result


def log_finalized(
    ctx: RequestContext,
    where: str,
    stats: FinalizeStats,
    truncated: bool,
    budget: Budget | None = None,
) -> None:
    """Сколько получили, сколько оставили и почему выкинули. Без текстов постов."""
    spent = f" spent={budget.seconds - budget.remaining():.1f}s" if budget else ""
    logger.info(
        "%s request_id=%s: got=%d kept=%d empty=%d outside_period=%d truncated=%s%s",
        where,
        ctx.request_id,
        stats.received,
        stats.kept,
        stats.empty_text,
        stats.outside_period,
        truncated,
        spent,
    )

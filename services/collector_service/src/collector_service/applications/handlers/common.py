"""Общее для хэндлеров сбора постов."""

import logging

from collector_service.applications.context import RequestContext
from collector_service.applications.exceptions import InvalidRequestError
from collector_service.domain.services import FinalizeStats
from collector_service.domain.value_objects import Period

logger = logging.getLogger(__name__)


def check_period(period: Period) -> None:
    if period.start > period.end:
        raise InvalidRequestError("Начало периода позже конца")


def log_finalized(ctx: RequestContext, where: str, stats: FinalizeStats, truncated: bool) -> None:
    """Сколько получили, сколько оставили и почему выкинули. Без текстов постов."""
    logger.info(
        "%s request_id=%s: got=%d kept=%d empty=%d outside_period=%d truncated=%s",
        where,
        ctx.request_id,
        stats.received,
        stats.kept,
        stats.empty_text,
        stats.outside_period,
        truncated,
    )

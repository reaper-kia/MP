"""Простой fixed-window rate limit на Redis. Если Redis лёг — пропускаем (fail-open)."""

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from gateway.config import Settings
from gateway.errors import ApiError

logger = logging.getLogger(__name__)


def rate_limit(
    name: str, limits: Callable[[Settings], tuple[int, int]]
) -> Callable[[Request], Awaitable[None]]:
    """limits(settings) -> (сколько запросов, за сколько секунд)."""

    async def dependency(request: Request) -> None:
        limit, window_seconds = limits(request.app.state.settings)
        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None or limit <= 0:
            return
        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{name}:{client_ip}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
        except RedisError as exc:
            logger.warning("Rate limiter unavailable: %s", exc)
            return
        if count > limit:
            raise ApiError(429, "RATE_LIMITED", "Too many requests, try again later")

    return dependency

import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Не чаще `per_second` запросов в секунду: каждый следующий ждёт свой слот.

    Часы и сон подставляются снаружи, чтобы тесты не ждали по-настоящему.
    per_second <= 0 — без ограничения.
    """

    def __init__(
        self,
        per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = 1.0 / per_second if per_second > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0

    async def wait(self) -> None:
        now = self._clock()
        slot = max(now, self._next_slot)  # между чтением и записью нет await — гонки нет
        self._next_slot = slot + self._interval
        if slot > now:
            await self._sleep(slot - now)

"""Бюджет времени на один сбор (B1-09 п. 2).

search_service ждёт одну цель 60 с и после этого считает её упавшей. Поэтому сборщик сам
заканчивает раньше и отдаёт то, что успел, с truncated и предупреждением, а не падает.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

# Запас на сериализацию ответа и сеть между сервисами
DEADLINE_MARGIN_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class Budget:
    seconds: float
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)
    started: float = field(default=-1.0, compare=False)

    @classmethod
    def start(
        cls,
        limit_seconds: float,
        time_remaining: float | None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "Budget":
        """Меньшее из своего лимита и дедлайна вызывающего (за вычетом запаса)."""
        seconds = limit_seconds
        if time_remaining is not None:
            seconds = min(seconds, max(time_remaining - DEADLINE_MARGIN_SECONDS, 0.0))
        return cls(seconds=seconds, clock=clock, started=clock())

    def remaining(self) -> float:
        return max(self.seconds - (self.clock() - self.started), 0.0)

    def expired(self) -> bool:
        return self.remaining() <= 0.0

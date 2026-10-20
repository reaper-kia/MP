"""Интерфейсы моделей и «автомат» (circuit breaker). Без настроек и сети — их импортирует core/."""

import logging
import time
from typing import Literal, Protocol

from ml_service.core.similarity import SimilarityThresholds

logger = logging.getLogger(__name__)

Kind = Literal["query", "doc"]


class LLM(Protocol):
    name: str

    @property
    def available(self) -> bool:
        """False — модель не подключена или недавно падала: сразу идём в эвристику."""
        ...

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Ответ модели строкой с JSON. Парсинг и валидация (pydantic) — у вызывающего.

        Ошибка сети / модели → MlUnavailableError.
        """
        ...

    async def aclose(self) -> None: ...


class Embedder(Protocol):
    name: str

    @property
    def thresholds(self) -> SimilarityThresholds:
        """Пороги косинуса для векторов ЭТОЙ модели (векторы разных моделей несравнимы)."""
        ...

    @property
    def available(self) -> bool: ...

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        """Векторы единичной длины (косинус = скалярное произведение), по одному на текст."""
        ...

    async def aclose(self) -> None: ...


class CircuitBreaker:
    """После сбоя модель «выключена» на cooldown секунд: не тратим бюджет RPC на таймаут."""

    def __init__(self, name: str, cooldown_seconds: float) -> None:
        self._name = name
        self._cooldown = cooldown_seconds
        self._open_until = 0.0
        self.reason = ""  # причина последнего сбоя — для лога переключений и /health

    @property
    def closed(self) -> bool:
        return time.monotonic() >= self._open_until

    def success(self) -> None:
        self._open_until = 0.0

    def failure(self, reason: str) -> None:
        self.reason = reason
        if self.closed:
            logger.warning(
                "%s недоступна (%s) — %.0f с её не вызываем (следующий провайдер или эвристики)",
                self._name,
                reason,
                self._cooldown,
            )
        self._open_until = time.monotonic() + self._cooldown

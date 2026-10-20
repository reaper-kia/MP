"""Цепочка провайдеров «ollama,yandex»: сначала Ollama (ноут через туннель), потом Yandex AI
Studio, потом эвристики (их делает движок, когда цепочка недоступна целиком).

Пользователь переключения не видит: ответ модели Яндекса — тоже ответ модели (degraded=false).
Нам видно: строка `ml provider switched: …` в логе и активный провайдер в HTTP /health.

LLM — по запросу: первый доступный, на MlUnavailableError — следующий. У каждого провайдера свой
«автомат» (CircuitBreaker): упавший 30 с не дёргаем, сразу идём к следующему.

Эмбеддинги — по ВЫЗОВУ: векторы bge-m3 и Яндекса несравнимы, поэтому в одном RPC все векторы от
одного провайдера. Движок берёт `candidates()` и работает с одним; упал посередине — весь вызов
заново на следующем (или без эмбеддингов). Смешивать векторы нельзя.
"""

import logging
from typing import Any

from ml_service.core.similarity import SimilarityThresholds
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import LLM, Embedder, Kind

logger = logging.getLogger(__name__)

STUB = "stub"


class _Switch:
    """Какой провайдер сейчас работает; меняется — строка в лог (INFO)."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.active: str | None = None  # None — ещё не вызывали
        self.reasons: dict[str, str] = {}

    def failed(self, name: str, reason: str) -> None:
        self.reasons[name] = reason

    def use(self, name: str) -> None:
        if name == self.active:
            return
        if self.active is None:
            logger.info("ml provider active: %s %s", self.role, name)
        else:
            reason = self.reasons.get(self.active, "недоступен")
            logger.info(
                "ml provider switched: %s %s → %s (%s)", self.role, self.active, name, reason
            )
        self.active = name


def _reason(e: BaseException) -> str:
    return (str(e) or type(e).__name__)[:200]


class FallbackLLM:
    def __init__(self, providers: list[LLM], role: str = "llm") -> None:
        if not providers:
            raise ValueError("пустая цепочка LLM")
        self.providers = providers
        self.name = " → ".join(p.name for p in providers)
        self._switch = _Switch(role)

    @property
    def available(self) -> bool:
        return any(p.available for p in self.providers)

    @property
    def active(self) -> str | None:
        return self._switch.active

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        errors: list[str] = []
        for provider in self.providers:
            if not provider.available:  # автомат выключил — даже не пробуем
                continue
            try:
                answer = await provider.complete_json(system, user, max_tokens=max_tokens)
            except MlUnavailableError as e:
                errors.append(_reason(e))
                self._switch.failed(provider.name, _reason(e))
                continue
            self._switch.use(provider.name)
            return answer
        self._switch.use(STUB)
        raise MlUnavailableError("; ".join(errors) or "все провайдеры LLM недоступны")

    def status(self) -> dict[str, Any]:
        return {
            "active": self._switch.active,
            "providers": [
                {
                    "name": p.name,
                    "available": p.available,
                    "last_error": self._switch.reasons.get(p.name, ""),
                }
                for p in self.providers
            ],
        }

    async def aclose(self) -> None:
        for provider in {id(p): p for p in self.providers}.values():
            await provider.aclose()


class FallbackEmbedder:
    """Сам векторы не смешивает: `embed` — целиком у одного провайдера; движок выбирает
    провайдера на весь RPC через `candidates()`."""

    def __init__(self, providers: list[Embedder], role: str = "embeddings") -> None:
        if not providers:
            raise ValueError("пустая цепочка эмбеддингов")
        self.providers = providers
        self.name = " → ".join(p.name for p in providers)
        self._switch = _Switch(role)

    @property
    def available(self) -> bool:
        return any(p.available for p in self.providers)

    @property
    def active(self) -> str | None:
        return self._switch.active

    @property
    def thresholds(self) -> SimilarityThresholds:
        """Пороги провайдера, который ответил бы сейчас (для одного провайдера — его)."""
        selected = self.select()
        return selected.thresholds if selected is not None else self.providers[0].thresholds

    def select(self) -> Embedder | None:
        """Первый доступный провайдер — с ним работает весь вызов."""
        return next((p for p in self.providers if p.available), None)

    def candidates(self) -> list[Embedder]:
        """Доступные по порядку: первый упал посреди вызова — весь вызов на следующем."""
        return [p for p in self.providers if p.available]

    def used(self, provider: Embedder) -> None:
        self._switch.use(provider.name)

    def failed(self, provider: Embedder, error: BaseException) -> None:
        self._switch.failed(provider.name, _reason(error))

    def exhausted(self) -> None:
        self._switch.use(STUB)

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        errors: list[str] = []
        for provider in self.candidates():
            try:
                vectors = await provider.embed(texts, kind)
            except MlUnavailableError as e:
                self.failed(provider, e)
                errors.append(_reason(e))
                continue
            self.used(provider)
            return vectors
        self.exhausted()
        raise MlUnavailableError("; ".join(errors) or "все провайдеры эмбеддингов недоступны")

    def status(self) -> dict[str, Any]:
        return {
            "active": self._switch.active,
            "providers": [
                {
                    "name": p.name,
                    "available": p.available,
                    "last_error": self._switch.reasons.get(p.name, ""),
                }
                for p in self.providers
            ],
        }

    async def aclose(self) -> None:
        for provider in {id(p): p for p in self.providers}.values():
            await provider.aclose()


def as_chain(embedder: Embedder) -> FallbackEmbedder:
    return embedder if isinstance(embedder, FallbackEmbedder) else FallbackEmbedder([embedder])

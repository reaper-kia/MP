"""LLM: stub (нет модели) и Ollama (/api/chat, format=json). Сборка по настройкам — build_llm."""

import logging
from typing import Any

import httpx

from ml_service.config import Settings
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import LLM, CircuitBreaker

logger = logging.getLogger(__name__)


class StubLLM:
    """Модели нет: available=False, движок сразу берёт эвристику (degraded=true)."""

    def __init__(self, reason: str = "LLM_PROVIDER=stub") -> None:
        self.name = "stub"
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        raise MlUnavailableError(f"LLM не подключена ({self.reason})")

    async def aclose(self) -> None:
        return None


class OllamaLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float,
        keep_alive: str,
        num_ctx: int,
        cooldown: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self._breaker = CircuitBreaker(self.name, cooldown)

    @property
    def available(self) -> bool:
        return self._breaker.closed

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": self._num_ctx},
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            self._breaker.failure(_describe(e))
            raise MlUnavailableError(f"{self.name}: {_describe(e)}") from e
        self._breaker.success()
        return str(content)

    async def aclose(self) -> None:
        await self._client.aclose()


def _describe(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        body = e.response.text[:200]
        return f"HTTP {e.response.status_code}: {body}"
    if isinstance(e, httpx.TimeoutException):
        return "таймаут"
    return f"{type(e).__name__}: {e}"[:200]


def build_llm(settings: Settings) -> LLM:
    """Никогда не бросает: неподключённый провайдер = stub с причиной в логе."""
    if settings.llm_provider == "ollama":
        return OllamaLLM(
            settings.ollama_url,
            settings.ollama_llm_model,
            timeout=settings.llm_timeout_seconds,
            keep_alive=settings.ollama_keep_alive,
            num_ctx=settings.ollama_num_ctx,
            cooldown=settings.breaker_cooldown_seconds,
        )
    if settings.llm_provider == "yandex":
        reason = "LLM_PROVIDER=yandex не реализован — команда работает на локальной модели (ollama)"
        logger.warning("%s; отвечаем эвристикой (degraded=true)", reason)
        return StubLLM(reason)
    return StubLLM()


def build_judge_llm(settings: Settings, main: LLM) -> LLM:
    """Отдельная (обычно меньшая) модель для ScorePosts, если задана OLLAMA_JUDGE_MODEL."""
    model = settings.ollama_judge_model.strip()
    if settings.llm_provider != "ollama" or not model or model == settings.ollama_llm_model:
        return main
    return OllamaLLM(
        settings.ollama_url,
        model,
        timeout=settings.llm_timeout_seconds,
        keep_alive=settings.ollama_keep_alive,
        num_ctx=settings.ollama_num_ctx,
        cooldown=settings.breaker_cooldown_seconds,
    )

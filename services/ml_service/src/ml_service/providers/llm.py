"""LLM: stub (нет модели), Ollama (/api/chat, format=json), Yandex (providers/yandex.py).

Сборка по настройкам — build_llm: LLM_PROVIDER — цепочка («ollama,yandex»), см. fallback.py.
"""

import logging
from typing import Any

import httpx

from ml_service.config import Provider, Settings
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import LLM, CircuitBreaker
from ml_service.providers.fallback import FallbackLLM
from ml_service.providers.liveness import Liveness, ollama_timeout
from ml_service.providers.yandex import YandexClient, YandexLLM

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
        connect_timeout: float = 0.0,
        probe_after: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=ollama_timeout(timeout, connect_timeout), transport=transport
        )
        self._breaker = CircuitBreaker(self.name, cooldown)
        self._liveness = Liveness(self._client, timeout=connect_timeout, after=probe_after)

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
            await self._liveness.check()
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            self._breaker.failure(_describe(e))
            raise MlUnavailableError(f"{self.name}: {_describe(e)}") from e
        self._breaker.success()
        self._liveness.ok()
        return str(content)

    async def aclose(self) -> None:
        await self._client.aclose()


def _describe(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        body = e.response.text[:200]
        return f"HTTP {e.response.status_code}: {body}"
    if isinstance(e, httpx.ConnectTimeout):
        return "не подключиться за connect-таймаут (ноут недоступен?)"
    if isinstance(e, httpx.ConnectError):
        return f"нет соединения: {e}"[:200]
    if isinstance(e, httpx.TimeoutException):
        return "таймаут"
    return f"{type(e).__name__}: {e}"[:200]


def build_llm(settings: Settings) -> LLM:
    """Никогда не бросает: неподключённый провайдер = stub с причиной в логе.

    Один провайдер — он сам (как раньше), несколько — FallbackLLM по порядку LLM_PROVIDER.
    """
    chain = [_one_llm(settings, name) for name in settings.llm_chain]
    return _chain(chain, "llm")


def build_judge_llm(settings: Settings, main: LLM) -> LLM:
    """Судья ScorePosts: та же цепочка, но с OLLAMA_JUDGE_MODEL / YC_JUDGE_MODEL, если заданы.

    Где отдельной модели нет — тот же объект, что у main (общий «автомат»).
    """
    mains = main.providers if isinstance(main, FallbackLLM) else [main]
    judges = [_one_judge(settings, base) for base in mains]
    if all(j is b for j, b in zip(judges, mains, strict=True)):
        return main
    return _chain(judges, "judge")


def _chain(chain: list[LLM], role: str) -> LLM:
    usable = [p for p in chain if not isinstance(p, StubLLM)]
    if not usable:
        return chain[0] if chain else StubLLM()
    return usable[0] if len(usable) == 1 else FallbackLLM(usable, role)


def _one_llm(settings: Settings, name: Provider) -> LLM:
    if name == "ollama":
        return _ollama_llm(settings, settings.ollama_llm_model)
    return _yandex_llm(settings, settings.yc_llm_model)


def _one_judge(settings: Settings, base: LLM) -> LLM:
    if isinstance(base, YandexLLM):
        judge = settings.yc_judge_model.strip()
        if not judge or judge == settings.yc_llm_model:
            return base
        return _yandex_llm(settings, judge)
    if isinstance(base, OllamaLLM):
        model = settings.ollama_judge_model.strip()
        if not model or model == settings.ollama_llm_model:
            return base
        return _ollama_llm(settings, model)
    return base


def _ollama_llm(settings: Settings, model: str) -> OllamaLLM:
    return OllamaLLM(
        settings.ollama_url,
        model,
        timeout=settings.llm_timeout_seconds,
        keep_alive=settings.ollama_keep_alive,
        num_ctx=settings.ollama_num_ctx,
        cooldown=settings.breaker_cooldown_seconds,
        connect_timeout=settings.ollama_connect_timeout_seconds,
        probe_after=settings.ollama_probe_after_seconds,
    )


def _yandex_llm(settings: Settings, model: str) -> LLM:
    if not (settings.yc_api_key and settings.yc_folder_id):
        reason = "yandex в LLM_PROVIDER, но не заданы YC_API_KEY / YC_FOLDER_ID"
        logger.warning("%s; этот провайдер пропускаем", reason)
        return StubLLM(reason)
    client = YandexClient(
        settings.yc_api_url,
        settings.yc_api_key,
        settings.yc_folder_id,
        timeout=settings.llm_timeout_seconds,
        retries=settings.yc_retries,
    )
    return YandexLLM(client, model, cooldown=settings.breaker_cooldown_seconds)

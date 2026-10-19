"""LLM за интерфейсом. Реализации yandex/ollama — ML-03/ML-05; до тех пор — stub (недоступна)."""

from typing import Protocol

from ml_service.config import Settings
from ml_service.errors import MlUnavailableError, ProviderNotConfiguredError


class LLM(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    async def complete_json(self, system: str, user: str) -> str:
        """Ответ модели строкой с JSON. Парсинг и валидация (pydantic) — у вызывающего."""
        ...


class StubLLM:
    name = "stub"

    @property
    def available(self) -> bool:
        return False

    async def complete_json(self, system: str, user: str) -> str:
        raise MlUnavailableError("LLM не подключена (LLM_PROVIDER=stub)")


def build_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "stub":
        return StubLLM()
    # TODO(ML-03): YandexLLM (yandex-cloud-ml-sdk) и OllamaLLM (httpx → /api/chat, format=json)
    raise ProviderNotConfiguredError(f"LLM_PROVIDER={settings.llm_provider} ещё не реализован")

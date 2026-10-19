"""Эмбеддинги за интерфейсом. Реализации yandex/ollama(bge-m3) — ML-04."""

from typing import Literal, Protocol

from ml_service.config import Settings
from ml_service.errors import MlUnavailableError, ProviderNotConfiguredError

Kind = Literal["query", "doc"]


class Embedder(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]: ...


class StubEmbedder:
    name = "stub"

    @property
    def available(self) -> bool:
        return False

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        raise MlUnavailableError("Эмбеддинги не подключены (EMBED_PROVIDER=stub)")


def build_embedder(settings: Settings) -> Embedder:
    if settings.embed_provider == "stub":
        return StubEmbedder()
    # TODO(ML-04): YandexEmbedder (text-search-query/doc), OllamaEmbedder (/api/embed, bge-m3)
    raise ProviderNotConfiguredError(f"EMBED_PROVIDER={settings.embed_provider} ещё не реализован")

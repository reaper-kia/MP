"""Эмбеддинги: stub, Ollama (/api/embed, bge-m3) и Yandex (providers/yandex.py).

EMBED_PROVIDER — цепочка, как LLM_PROVIDER (пусто — та же, что у LLM), см. fallback.py.

Кэш в памяти — ScorePosts и GroupPosts эмбеддят одни и те же тексты, второй раз это бесплатно.
"""

import hashlib
import logging
import math
from collections import OrderedDict
from typing import Any

import httpx

from ml_service.config import Provider, Settings
from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import CircuitBreaker, Embedder, Kind
from ml_service.providers.fallback import FallbackEmbedder
from ml_service.providers.liveness import Liveness, ollama_timeout

logger = logging.getLogger(__name__)

CACHE_SIZE = 20_000


class StubEmbedder:
    def __init__(self, reason: str = "EMBED_PROVIDER=stub") -> None:
        self.name = "stub"
        self.reason = reason
        self.thresholds = BGE_M3

    @property
    def available(self) -> bool:
        return False

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        raise MlUnavailableError(f"Эмбеддинги не подключены ({self.reason})")

    async def aclose(self) -> None:
        return None


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm > 0 else vector


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float,
        keep_alive: str,
        batch_size: int,
        cooldown: float,
        thresholds: SimilarityThresholds = BGE_M3,
        connect_timeout: float = 0.0,
        probe_after: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self.thresholds = thresholds
        self._keep_alive = keep_alive
        self._batch = max(1, batch_size)
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=ollama_timeout(timeout, connect_timeout), transport=transport
        )
        self._breaker = CircuitBreaker(self.name, cooldown)
        self._liveness = Liveness(self._client, timeout=connect_timeout, after=probe_after)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    @property
    def available(self) -> bool:
        return self._breaker.closed

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        # bge-m3 не различает запрос и документ — kind в ключе кэша на случай другой модели
        keys = [_key(kind, t) for t in texts]
        missing = [i for i, k in enumerate(keys) if k not in self._cache]
        unique: dict[str, int] = {}
        for i in missing:
            unique.setdefault(keys[i], i)
        order = list(unique.items())
        for start in range(0, len(order), self._batch):
            chunk = order[start : start + self._batch]
            vectors = await self._request([texts[i] for _, i in chunk])
            for (key, _), vector in zip(chunk, vectors, strict=True):
                self._put(key, normalize(vector))
        result = []
        for key in keys:
            vector = self._cache[key]
            self._cache.move_to_end(key)
            result.append(vector)
        return result

    async def _request(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "keep_alive": self._keep_alive,
            "truncate": True,
        }
        try:
            await self._liveness.check()
            response = await self._client.post("/api/embed", json=payload)
            response.raise_for_status()
            vectors = response.json()["embeddings"]
            if len(vectors) != len(texts):
                raise ValueError(f"ждали {len(texts)} векторов, пришло {len(vectors)}")
            parsed = [[float(x) for x in v] for v in vectors]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            reason = f"{type(e).__name__}: {e}"[:200]
            self._breaker.failure(reason)
            raise MlUnavailableError(f"{self.name}: {reason}") from e
        self._breaker.success()
        self._liveness.ok()
        return parsed

    def _put(self, key: str, vector: list[float]) -> None:
        self._cache[key] = vector
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    async def aclose(self) -> None:
        await self._client.aclose()


def _key(kind: Kind, text: str) -> str:
    return kind + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_embedder(settings: Settings) -> Embedder:
    """Никогда не бросает: неподключённый провайдер = stub с причиной в логе.

    Один провайдер — он сам, несколько — FallbackEmbedder (один RPC — один провайдер).
    """
    chain = [_one_embedder(settings, name) for name in settings.embed_chain]
    usable = [e for e in chain if not isinstance(e, StubEmbedder)]
    if not usable:
        return chain[0] if chain else StubEmbedder()
    return usable[0] if len(usable) == 1 else FallbackEmbedder(usable)


def _one_embedder(settings: Settings, name: Provider) -> Embedder:
    if name == "ollama":
        return OllamaEmbedder(
            settings.ollama_url,
            settings.ollama_embed_model,
            timeout=settings.embed_timeout_seconds,
            keep_alive=settings.ollama_keep_alive,
            batch_size=settings.embed_batch_size,
            cooldown=settings.breaker_cooldown_seconds,
            thresholds=SimilarityThresholds(
                settings.sim_low, settings.sim_high, settings.sim_retell, settings.sim_same_news
            ),
            connect_timeout=settings.ollama_connect_timeout_seconds,
            probe_after=settings.ollama_probe_after_seconds,
        )
    if not (settings.yc_api_key and settings.yc_folder_id):
        reason = "yandex в EMBED_PROVIDER, но не заданы YC_API_KEY / YC_FOLDER_ID"
        logger.warning("%s; этот провайдер эмбеддингов пропускаем", reason)
        return StubEmbedder(reason)
    # импорт здесь: yandex.py берёт normalize из этого модуля
    from ml_service.providers.yandex import YandexClient, YandexEmbedder

    client = YandexClient(
        settings.yc_api_url,
        settings.yc_api_key,
        settings.yc_folder_id,
        timeout=settings.embed_timeout_seconds,
        retries=settings.yc_retries,
    )
    return YandexEmbedder(
        client,
        doc_model=settings.yc_embed_doc_model,
        query_model=settings.yc_embed_query_model,
        concurrency=settings.yc_embed_concurrency,
        cooldown=settings.breaker_cooldown_seconds,
        thresholds=SimilarityThresholds(
            settings.sim_low_yandex,
            settings.sim_high_yandex,
            settings.sim_retell_yandex,
            settings.sim_same_news_yandex,
        ),
    )

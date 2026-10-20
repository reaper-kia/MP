"""Модели Yandex AI Studio (Foundation Models API): YandexGPT и эмбеддинги text-search.

Зачем: на сервере без GPU локальная модель не успевает в бюджеты, а API Яндекса отвечает за
секунды и не требует железа. ТЗ рекомендует продукты Яндекса.

LLM        → POST {api}/foundationModels/v1/completion
             modelUri gpt://<folder>/yandexgpt-lite/latest, jsonObject=true, temperature=0
Эмбеддинги → POST {api}/foundationModels/v1/textEmbedding — один текст на запрос
             запрос: emb://<folder>/text-search-query/latest, пост: …/text-search-doc/latest
Авторизация — API-ключ сервисного аккаунта (`Authorization: Api-Key …`), роль
`ai.languageModels.user` на каталоге. Что уходит в Яндекс: текст запроса и тексты публичных постов.

429 (лимит запросов) и 5xx повторяем с паузой; остальное — сразу MlUnavailableError, «автомат»
выключает провайдер на cooldown, движок отвечает эвристикой.
"""

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Any

import httpx

from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import CircuitBreaker, Kind
from ml_service.providers.embeddings import normalize

logger = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
CACHE_SIZE = 20_000


class YandexClient:
    """Общий HTTP-клиент: заголовки, повторы на 429/5xx, понятные причины ошибок."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        folder_id: str,
        *,
        timeout: float,
        retries: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.folder_id = folder_id
        self._retries = max(0, retries)
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id},
        )

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        for attempt in range(self._retries + 1):
            response = await self._client.post(path, json=payload)
            if response.status_code in RETRY_STATUSES and attempt < self._retries:
                await _pause(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        raise httpx.HTTPError("повторы исчерпаны")  # недостижимо: последний ответ уже поднят

    async def aclose(self) -> None:
        await self._client.aclose()


async def _pause(seconds: float) -> None:
    """Пауза перед повтором (в тестах подменяется)."""
    await asyncio.sleep(seconds)


def describe(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return f"HTTP {code}: ключ не принят — проверьте YC_API_KEY и роль на каталоге"
        if code == 429:
            return "HTTP 429: превышен лимит запросов Yandex AI Studio"
        return f"HTTP {code}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "таймаут"
    return f"{type(e).__name__}: {e}"[:200]


class YandexLLM:
    def __init__(
        self,
        client: YandexClient,
        model: str,
        *,
        cooldown: float,
    ) -> None:
        # model — «yandexgpt-lite/latest» или полный «gpt://…» URI
        self.model_uri = model if "://" in model else f"gpt://{client.folder_id}/{model}"
        self.name = f"yandex:{model}"
        self._client = client
        self._breaker = CircuitBreaker(self.name, cooldown)

    @property
    def available(self) -> bool:
        return self._breaker.closed

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        payload: dict[str, Any] = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": 0,
                "maxTokens": str(max_tokens),  # в API — строка (int64)
            },
            "messages": [
                {"role": "system", "text": system},
                {"role": "user", "text": user},
            ],
            "jsonObject": True,
        }
        try:
            data = await self._client.post("/foundationModels/v1/completion", payload)
            alternative = data["result"]["alternatives"][0]
            status = alternative.get("status", "")
            if status == "ALTERNATIVE_STATUS_CONTENT_FILTER":
                raise ValueError("ответ скрыт фильтром содержимого Яндекса")
            text = alternative["message"]["text"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
            # фильтр содержимого — про конкретный текст, а не про модель: автомат не выключаем
            if not (isinstance(e, ValueError) and "фильтром" in str(e)):
                self._breaker.failure(describe(e))
            raise MlUnavailableError(f"{self.name}: {describe(e)}") from e
        self._breaker.success()
        return str(text)

    async def aclose(self) -> None:
        await self._client.aclose()


class YandexEmbedder:
    """Векторы text-search-query / text-search-doc. Один текст — один запрос, поэтому
    параллельно (concurrency) и с кэшем: GroupPosts и ScorePosts эмбеддят одни и те же посты."""

    def __init__(
        self,
        client: YandexClient,
        *,
        doc_model: str,
        query_model: str,
        concurrency: int,
        cooldown: float,
        thresholds: SimilarityThresholds = BGE_M3,
    ) -> None:
        folder = client.folder_id
        # пороги косинуса этой модели: SIM_*_YANDEX (до калибровки ML-11 — как у bge-m3)
        self.thresholds = thresholds
        self._uri: dict[Kind, str] = {
            "doc": doc_model if "://" in doc_model else f"emb://{folder}/{doc_model}",
            "query": query_model if "://" in query_model else f"emb://{folder}/{query_model}",
        }
        self.name = f"yandex:{doc_model.split('/')[0]}"
        self._client = client
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._breaker = CircuitBreaker(self.name, cooldown)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    @property
    def available(self) -> bool:
        return self._breaker.closed

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        keys = [_key(kind, t) for t in texts]
        todo: dict[str, str] = {}
        for key, text in zip(keys, texts, strict=True):
            if key not in self._cache:
                todo.setdefault(key, text)
        if todo:
            try:
                vectors = await asyncio.gather(*(self._one(text, kind) for text in todo.values()))
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
                self._breaker.failure(describe(e))
                raise MlUnavailableError(f"{self.name}: {describe(e)}") from e
            for key, vector in zip(todo, vectors, strict=True):
                self._put(key, normalize(vector))
            self._breaker.success()
        result = []
        for key in keys:
            self._cache.move_to_end(key)
            result.append(self._cache[key])
        return result

    async def _one(self, text: str, kind: Kind) -> list[float]:
        async with self._sem:
            data = await self._client.post(
                "/foundationModels/v1/textEmbedding",
                {"modelUri": self._uri[kind], "text": text or " "},
            )
        vector = [float(x) for x in data["embedding"]]
        if not vector:
            raise ValueError("пустой вектор")
        return vector

    def _put(self, key: str, vector: list[float]) -> None:
        self._cache[key] = vector
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    async def aclose(self) -> None:
        await self._client.aclose()


def _key(kind: Kind, text: str) -> str:
    return kind + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()

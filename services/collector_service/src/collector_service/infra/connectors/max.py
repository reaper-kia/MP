"""MAX через Bot API (B1-05). Почему не веб: проба 2026-10-19 — max.ru/<канал> без логина отдаёт
одинаковую заглушку приложения, __data.json — пустой linkInfo; постов, дат и ссылок нет
(docs/collector-spike.md). Bot API отдаёт посты только тех каналов, где бот — администратор.

resolve  → GET /chats/{handle} (канал по публичной ссылке max.ru/<handle>)
collect  → GET /messages?chat_id=…&count=100, страницами от новых к старым (from = момент,
           с которого листаем назад), пока посты не станут старше начала периода
search   → глобального поиска в Bot API нет; через Яндекс тоже нечем открыть пост
           (страницы без логина пустые) — режим «везде» для MAX не поддерживается
"""

import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    CollectorError,
    PlatformUnavailableError,
    RateLimitedError,
    UnsupportedUrlError,
)
from collector_service.domain.messages import source_not_found
from collector_service.domain.urls import path_parts
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    RawPost,
    SourceInfo,
)
from collector_service.infra.cache import HealthCache
from collector_service.infra.max_api.client import MaxApiClient
from collector_service.infra.max_api.mapping import MAX_URL, post_from_message, source_from_chat

PAGE = 100  # максимум count в GET /messages
MAX_PAGES = 30
NO_TOKEN_NOTE = (
    "Не настроен доступ к MAX (MAX_BOT_TOKEN). Без бота посты каналов недоступны: "
    "веб-страницы MAX без входа постов не показывают"
)
GLOBAL_NOTE = "Поиск «везде» в MAX невозможен: у Bot API нет поиска, веб без входа пуст"


class MaxConnector:
    platform = Platform.MAX
    title = "MAX"
    hosts: tuple[str, ...] = ("max.ru",)

    def __init__(self, api: MaxApiClient, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._api = api
        self._health = HealthCache(clock)
        self._names: dict[str, tuple[str, str]] = {}  # chat_id → (название, ссылка)

    # ---------- health ----------

    async def health(self) -> PlatformInfo:
        return await self._health.get(self._check_health)

    async def _check_health(self) -> PlatformInfo:
        if not self._api.configured:
            return self._info(Health.UNAVAILABLE, NO_TOKEN_NOTE)
        try:
            await self._api.get("/me")
        except RateLimitedError:
            return self._info(Health.DEGRADED, "MAX ограничивает частоту запросов")
        except CollectorError as exc:
            return self._info(Health.UNAVAILABLE, str(exc))
        return self._info(
            Health.OK, f"Только каналы, где бот сервиса — администратор. {GLOBAL_NOTE}"
        )

    def _info(self, health: Health, note: str) -> PlatformInfo:
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=health is not Health.UNAVAILABLE,
            global_mode_supported=False,
            health=health,
            note=note,
        )

    # ---------- resolve ----------

    async def resolve(self, url: str) -> SourceInfo:
        parts = path_parts(url)
        if len(parts) != 1:
            raise UnsupportedUrlError("Ожидается ссылка на канал вида max.ru/имя_канала")
        handle = parts[0]
        chat = await self._api.get(f"/chats/{handle}")
        if "chat_id" not in chat:
            raise UnsupportedUrlError("MAX: по ссылке не канал")
        source = source_from_chat(chat, handle)
        self._names[source.external_id] = (source.name, source.url)
        return source

    # ---------- collect ----------

    async def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        chat_id = source_external_id.strip()
        if not chat_id.lstrip("-").isdigit():
            raise UnsupportedUrlError(
                source_not_found(self.title), detail=f"MAX: некорректный id {chat_id!r}"
            )
        name, source_url = await self._name(chat_id)
        start_ms = int(period.start.timestamp() * 1000)
        cursor = int(period.end.timestamp() * 1000)
        for _ in range(MAX_PAGES):
            response = await self._api.get(
                "/messages", chat_id=chat_id, count=PAGE, to=start_ms, **{"from": cursor}
            )
            messages = _messages(response)
            if not messages:
                return
            posts: list[RawPost] = []
            skipped = 0
            for message in messages:
                post = post_from_message(message, chat_id, name, source_url)
                if post is None:
                    skipped += 1
                else:
                    posts.append(post)
            warnings = (
                [f"MAX: пропущено сообщений без ссылки на пост: {skipped}"] if skipped else []
            )
            yield Page(posts=posts, warnings=warnings)
            oldest = min(_ts(m) for m in messages)
            if oldest <= start_ms or oldest >= cursor or len(messages) < PAGE:
                return
            cursor = oldest - 1
        yield Page(
            truncated=True,
            warnings=["MAX: достигнут предел глубины канала — старые посты не проверены"],
        )

    async def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        raise PlatformUnavailableError(GLOBAL_NOTE)
        yield Page()  # pragma: no cover

    async def _name(self, chat_id: str) -> tuple[str, str]:
        cached = self._names.get(chat_id)
        if cached:
            return cached
        chat = await self._api.get(f"/chats/{chat_id}")
        title = chat.get("title") if isinstance(chat.get("title"), str) else None
        link = chat.get("link") if isinstance(chat.get("link"), str) else None
        names = (title or f"MAX {chat_id}", link or MAX_URL)
        self._names[chat_id] = names
        return names


def _messages(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = response.get("messages")
    return [m for m in raw if isinstance(m, Mapping)] if isinstance(raw, list) else []


def _ts(message: Mapping[str, Any]) -> int:
    value = message.get("timestamp")
    return value if isinstance(value, int) else 0

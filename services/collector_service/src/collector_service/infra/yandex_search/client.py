"""Клиент Yandex Search API v2: POST /v2/web/search → ссылки, заголовки, фрагменты.

Документация: https://aistudio.yandex.ru/docs/ru/search-api/ (WebSearch.Search).
Авторизация — заголовок `Authorization: Api-Key <ключ>` сервисного аккаунта с ролью
`search-api.webSearch.user`; каталог — `folderId` в теле. Ответ — `rawData`: XML в base64
(тот же формат, что у старого XML-поиска Яндекса).

Здесь только ссылки из выдачи. Дату и текст поста поисковик не даёт — их достаёт коннектор
площадки, открыв страницу (правило достоверности: не открылось — в ответ не идёт).
"""

import base64
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from collector_service.domain import messages
from collector_service.domain.exceptions import (
    CollectorError,
    PlatformUnavailableError,
    RateLimitedError,
)
from collector_service.infra.vk_api.limiter import RateLimiter

logger = logging.getLogger(__name__)

API_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
MAX_QUERY_LENGTH = 400  # символов; и не больше 40 слов (ограничение API)


@dataclass(frozen=True, slots=True)
class SearchHit:
    url: str
    title: str
    snippet: str


class JsonPoster(Protocol):
    async def post_json(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> tuple[int, Any]:
        """(HTTP-статус, разобранный JSON или None). Сетевые сбои — CollectorError."""
        ...


class YandexSearchClient:
    def __init__(
        self,
        poster: JsonPoster,
        *,
        folder_id: str,
        api_key: str,
        region: int | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._poster = poster
        self._folder_id = folder_id
        self._api_key = api_key
        self._region = region
        self._limiter = limiter or RateLimiter(5.0)  # квота API — 10 запросов/с

    @property
    def configured(self) -> bool:
        return bool(self._folder_id and self._api_key)

    async def search(self, query_text: str, page: int = 0) -> list[SearchHit]:
        if not self.configured:
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_NOT_CONFIGURED,
                detail="Яндекс Поиск: не заданы YC_FOLDER_ID / YC_SEARCH_API_KEY",
            )
        body: dict[str, Any] = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query_text[:MAX_QUERY_LENGTH],
                "familyMode": "FAMILY_MODE_NONE",
                "page": str(page),
            },
            "sortSpec": {"sortMode": "SORT_MODE_BY_TIME", "sortOrder": "SORT_ORDER_DESC"},
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": "100",
                "docsInGroup": "1",
            },
            "maxPassages": "2",
            "l10n": "LOCALIZATION_RU",
            "folderId": self._folder_id,
            "responseFormat": "FORMAT_XML",
        }
        if self._region is not None:
            body["region"] = str(self._region)
        await self._limiter.wait()
        status, payload = await self._poster.post_json(
            API_URL, body, {"Authorization": f"Api-Key {self._api_key}"}
        )
        if status == 429:
            raise RateLimitedError(
                messages.GLOBAL_SEARCH_QUOTA, detail="Яндекс Поиск: 429, превышена квота запросов"
            )
        if status in (401, 403):
            # причину Яндекс пишет в message («Permission denied», «billing account…») — без неё
            # не понять, что чинить: ключ, роль сервисного аккаунта или биллинг
            reason = payload.get("message") if isinstance(payload, Mapping) else None
            detail = f": {str(reason)[:160]}" if reason else ""
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_DENIED,
                detail=(
                    f"Яндекс Поиск: ключ не принят ({status}{detail}) — проверьте "
                    "YC_SEARCH_API_KEY, роль search-api.webSearch.user и биллинг"
                ),
            )
        if status >= 400 or not isinstance(payload, Mapping):
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_DOWN, detail=f"Яндекс Поиск: ошибка HTTP {status}"
            )
        raw = payload.get("rawData")
        if not isinstance(raw, str):
            return []
        try:
            return parse_xml(base64.b64decode(raw))
        except (ValueError, CollectorError) as exc:
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_DOWN, detail=f"Яндекс Поиск: непонятный ответ ({exc})"
            ) from None


def parse_xml(data: bytes) -> list[SearchHit]:
    """XML выдачи Яндекса → ссылки. Ошибка в самом ответе (<error>) — пусто или исключение.

    Код 15 «ничего не найдено» — нормальный пустой ответ.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"XML: {exc}") from None
    error = root.find("./response/error")
    if error is not None:
        if error.get("code") == "15":
            return []
        raise PlatformUnavailableError(
            messages.GLOBAL_SEARCH_DOWN,
            detail=f"Яндекс Поиск: ошибка {error.get('code')} в ответе: {_text(error)}",
        )
    hits: list[SearchHit] = []
    for doc in root.iterfind(".//results/grouping/group/doc"):
        url = _text(doc.find("url"))
        if not url:
            continue
        passages = [_text(p) for p in doc.iterfind("./passages/passage")]
        hits.append(
            SearchHit(
                url=url,
                title=_text(doc.find("title")),
                snippet=" … ".join(p for p in passages if p),
            )
        )
    return hits


def _text(node: Element | None) -> str:
    """Текст узла вместе с <hlword> внутри."""
    return " ".join("".join(node.itertext()).split()) if node is not None else ""

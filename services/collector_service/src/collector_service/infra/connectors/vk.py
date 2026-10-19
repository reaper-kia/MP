"""ВКонтакте через VK API (сервисный ключ). Задачи B1-03 и B1-07 (health).

resolve  → groups.getById(group_id, fields=city,members_count,is_closed)
collect  → wall.get(owner_id, count=100, offset) пока посты новее period.start
           (закреплённый пост идёт первым и может быть старым — на нём не останавливаемся)
search   → newsfeed.search(q, start_time, end_time, count=200, start_from) по каждой фразе

Чего коннектор НЕ делает (это работа соседей):
- `keywords` в collect игнорируются: отдаём все посты за период, отбор по смыслу — ML (ScorePosts);
- `region_terms` в search игнорируются: фразы приходят от ML как есть, ищем по всему открытому VK,
  а привязку к региону определяют ML и search_service.
Соответствие полей VK → RawPost — infra/vk_api/mapping.py и docs/tasks/B1-collector.md (B1-03).
"""

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    CollectorError,
    RateLimitedError,
    SourceNotFoundError,
)
from collector_service.domain.value_objects import (
    CollectResult,
    Period,
    PlatformInfo,
    RawPost,
    SourceInfo,
)
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.mapping import (
    SourceCard,
    card_from_group,
    card_from_user,
    fallback_card,
    group_items,
    group_ref_from_url,
    owner_id_from_external,
    post_from_item,
    source_from_group,
    user_items,
)

logger = logging.getLogger(__name__)

WALL_PAGE = 100  # максимум wall.get
WALL_MAX_PAGES = 50  # страховка: не листаем стену глубже 5000 постов
SEARCH_PAGE = 200  # максимум newsfeed.search
SEARCH_MAX_PAGES = 5  # VK отдаёт не больше ~1000 результатов на запрос
CARDS_BATCH = 500  # groups.getById / users.get принимают до 500 / 1000 id
HEALTH_OK_TTL = 300.0  # кэш «здорова» — 5 минут (B1-07)
HEALTH_FAIL_TTL = 60.0  # проблему перепроверяем чаще: она может пройти сама

GROUP_FIELDS = "city,members_count,is_closed"


class VkConnector:
    platform = Platform.VK
    title = "ВКонтакте"
    hosts: tuple[str, ...] = ("vk.com", "vk.ru")

    def __init__(self, api: VkApiClient, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._api = api
        self._clock = clock
        self._health: tuple[float, PlatformInfo] | None = None

    # ---------- health (B1-07) ----------

    async def health(self) -> PlatformInfo:
        now = self._clock()
        if self._health is not None and now < self._health[0]:
            return self._health[1]
        info = await self._check_health()
        ttl = HEALTH_OK_TTL if info.health is Health.OK else HEALTH_FAIL_TTL
        self._health = (now + ttl, info)
        return info

    async def _check_health(self) -> PlatformInfo:
        if not self._api.configured:
            return self._info(
                Health.UNAVAILABLE, "Не настроен доступ к ВКонтакте (VK_SERVICE_TOKEN)"
            )
        try:
            await self._api.call("users.get", user_ids=1)  # дешёвый запрос, проверяет ключ
        except RateLimitedError:
            return self._info(Health.DEGRADED, "ВКонтакте ограничивает частоту запросов")
        except CollectorError as exc:
            return self._info(Health.UNAVAILABLE, str(exc))
        return self._info(Health.OK, "")

    def _info(self, health: Health, note: str) -> PlatformInfo:
        working = health is not Health.UNAVAILABLE
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=working,
            global_mode_supported=working,
            health=health,
            note=note,
        )

    # ---------- resolve ----------

    async def resolve(self, url: str) -> SourceInfo:
        ref = group_ref_from_url(url)
        response = await self._api.call("groups.getById", group_id=ref, fields=GROUP_FIELDS)
        groups = group_items(response)
        if not groups:
            raise SourceNotFoundError("Сообщество не найдено на ВКонтакте")
        return source_from_group(groups[0])

    # ---------- collect ----------

    async def collect(
        self,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        owner_id = owner_id_from_external(source_external_id)
        card = (await self._cards([owner_id])).get(owner_id)
        if card is None:
            raise SourceNotFoundError("Источник не найден на ВКонтакте")
        start_ts = int(period.start.timestamp())
        result = CollectResult()
        skipped_empty = 0
        offset = 0

        for _ in range(WALL_MAX_PAGES):
            response = await self._api.call(
                "wall.get", owner_id=owner_id, count=WALL_PAGE, offset=offset
            )
            items = _items(response)
            if not items:
                return _done(result, skipped_empty)
            for item in items:
                date = item.get("date")
                if isinstance(date, int) and date < start_ts and not item.get("is_pinned"):
                    return _done(result, skipped_empty)  # дальше только старее
                post = post_from_item(item, card)
                if post is None or not _in_period(post, period):
                    continue
                if not post.text:
                    skipped_empty += 1
                    continue
                if len(result.posts) >= max_posts:
                    result.truncated = True
                    return _done(result, skipped_empty)
                result.posts.append(post)
            offset += len(items)
            total = response.get("count") if isinstance(response, Mapping) else None
            if isinstance(total, int) and offset >= total:
                return _done(result, skipped_empty)

        result.truncated = True
        result.warnings.append(
            "Достигнут предел глубины просмотра стены — старые посты не проверены"
        )
        return _done(result, skipped_empty)

    # ---------- search ----------

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        found: dict[tuple[int, int], Mapping[str, Any]] = {}  # дубли между фразами → один пост
        truncated = False
        warnings: list[str] = []
        first_error: CollectorError | None = None
        succeeded = 0

        for query in queries:
            try:
                truncated |= await self._search_phrase(query, period, max_posts, found)
            except CollectorError as exc:
                first_error = first_error or exc
                warnings.append(f"Фраза «{query}» не обработана: {exc}")
                continue
            succeeded += 1
            if truncated:
                break
        if succeeded == 0 and first_error is not None:
            raise first_error

        owners = {int(item["owner_id"]) for item in found.values()}
        cards = await self._cards_or_empty(owners, warnings)
        result = CollectResult(truncated=truncated, warnings=warnings)
        skipped_empty = 0
        for item in found.values():
            owner_id = int(item["owner_id"])
            post = post_from_item(item, cards.get(owner_id) or fallback_card(owner_id))
            if post is None:
                continue
            if not post.text:
                skipped_empty += 1
                continue
            result.posts.append(post)
        return _done(result, skipped_empty)

    async def _search_phrase(
        self,
        query: str,
        period: Period,
        max_posts: int,
        found: dict[tuple[int, int], Mapping[str, Any]],
    ) -> bool:
        """Добавляет найденное в `found`. True — упёрлись в max_posts."""
        params: dict[str, str | int] = {
            "q": query,
            "start_time": int(period.start.timestamp()),
            "end_time": int(period.end.timestamp()),
            "count": SEARCH_PAGE,
        }
        for _ in range(SEARCH_MAX_PAGES):
            response = await self._api.call("newsfeed.search", **params)
            items = _items(response)
            for item in items:
                owner_id, post_id = item.get("owner_id"), item.get("id")
                if not isinstance(owner_id, int) or not isinstance(post_id, int):
                    continue
                key = (owner_id, post_id)
                if key not in found and len(found) >= max_posts:
                    return True
                found.setdefault(key, item)
            next_from = response.get("next_from") if isinstance(response, Mapping) else None
            if not items or not next_from:
                break
            params["start_from"] = str(next_from)
        return False

    # ---------- названия источников ----------

    async def _cards(self, owner_ids: Iterable[int]) -> dict[int, SourceCard]:
        """Карточки источников: сообщества — groups.getById, люди — users.get (пачками).

        Ошибки VK не глотаем; id, которого VK не вернул, в результат просто не попадает.
        """
        ids = sorted(set(owner_ids))
        groups = [str(-i) for i in ids if i < 0]
        users = [str(i) for i in ids if i > 0]
        cards: dict[int, SourceCard] = {}
        for batch in _batches(groups, CARDS_BATCH):
            response = await self._api.call("groups.getById", group_ids=",".join(batch))
            cards.update(card_from_group(item) for item in group_items(response))
        for batch in _batches(users, CARDS_BATCH):
            response = await self._api.call("users.get", user_ids=",".join(batch))
            cards.update(card_from_user(item) for item in user_items(response))
        return cards

    async def _cards_or_empty(
        self, owner_ids: set[int], warnings: list[str]
    ) -> dict[int, SourceCard]:
        """Для поиска: сбой на названиях не должен терять найденные посты."""
        try:
            cards = await self._cards(owner_ids)
        except CollectorError as exc:
            warnings.append(f"Названия источников получены не полностью: {exc}")
            return {}
        if missing := len(owner_ids) - len(cards):
            warnings.append(f"Не удалось получить названия источников: {missing}")
        return cards


def _items(response: Any) -> list[Mapping[str, Any]]:
    raw = response.get("items") if isinstance(response, Mapping) else None
    return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _in_period(post: RawPost, period: Period) -> bool:
    return post.published_at is None or period.contains(post.published_at)


def _done(result: CollectResult, skipped_empty: int) -> CollectResult:
    if skipped_empty:
        result.warnings.append(f"Пропущено постов без текста: {skipped_empty}")
    return result


def _batches(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]

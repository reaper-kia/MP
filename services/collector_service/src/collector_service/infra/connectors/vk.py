"""ВКонтакте через VK API (сервисный ключ). Задачи B1-03 и B1-07 (health).

resolve  → groups.getById(group_id, fields=city,members_count,is_closed)
collect  → wall.get(owner_id, count=100, offset) пока посты новее period.start
           (закреплённый пост идёт первым и может быть старым — на нём не останавливаемся)
search   → newsfeed.search(q, start_time, end_time, count=200, start_from) по каждой фразе
read_post→ wall.getById(posts, extended=1): PostReader для «везде» через Яндекс (site:vk.com),
           когда newsfeed.search ключу закрыт (токен пользователя VK ID — ошибка 1051)

Чего коннектор НЕ делает (это работа соседей):
- `keywords` в collect игнорируются: отдаём все посты за период, отбор по смыслу — ML (ScorePosts);
- `region_terms` в search игнорируются: фразы приходят от ML как есть, ищем по всему открытому VK,
  а привязку к региону определяют ML и search_service.
Соответствие полей VK → RawPost — infra/vk_api/mapping.py и docs/tasks/B1-collector.md (B1-03).
"""

import logging
import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    CollectorError,
    MethodUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
)
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    RawPost,
    SourceInfo,
)
from collector_service.infra.cache import HealthCache
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
    wall_ref_from_url,
)

logger = logging.getLogger(__name__)

WALL_PAGE = 100  # максимум wall.get
WALL_MAX_PAGES = 50  # страховка: не листаем стену глубже 5000 постов
SEARCH_PAGE = 200  # максимум newsfeed.search
SEARCH_MAX_PAGES = 5  # VK отдаёт не больше ~1000 результатов на запрос
CARDS_BATCH = 500  # groups.getById / users.get принимают до 500 / 1000 id

GROUP_FIELDS = "city,members_count,is_closed"


class VkConnector:
    platform = Platform.VK
    title = "ВКонтакте"
    hosts: tuple[str, ...] = ("vk.com", "vk.ru")

    def __init__(self, api: VkApiClient, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._api = api
        self._health = HealthCache(clock)

    # ---------- health (B1-07) ----------

    async def health(self) -> PlatformInfo:
        return await self._health.get(self._check_health)

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
    ) -> AsyncIterator[Page]:
        """Страница wall.get за страницей, пока посты не станут старше начала периода.

        Период, пустые тексты и лимит применяет потребитель; здесь — только где остановиться.
        """
        owner_id = owner_id_from_external(source_external_id)
        card = (await self._cards([owner_id])).get(owner_id)
        if card is None:
            raise SourceNotFoundError("Источник не найден на ВКонтакте")
        start_ts = int(period.start.timestamp())
        offset = 0

        for _ in range(WALL_MAX_PAGES):
            response = await self._api.call(
                "wall.get", owner_id=owner_id, count=WALL_PAGE, offset=offset
            )
            items = _items(response)
            if not items:
                return
            posts: list[RawPost] = []
            reached_old = False
            for item in items:
                date = item.get("date")
                if isinstance(date, int) and date < start_ts and not item.get("is_pinned"):
                    reached_old = True  # дальше только старее
                    break
                post = post_from_item(item, card)
                if post is not None:
                    posts.append(post)
            yield Page(posts=posts)
            if reached_old:
                return
            offset += len(items)
            total = response.get("count") if isinstance(response, Mapping) else None
            if isinstance(total, int) and offset >= total:
                return

        yield Page(
            truncated=True,
            warnings=["Достигнут предел глубины просмотра стены — старые посты не проверены"],
        )

    # ---------- search ----------

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
    ) -> AsyncIterator[Page]:
        """По странице на фразу: найденное + названия источников (пачкой на фразу).

        Упавшая фраза не роняет поиск: её ошибка уходит в warnings следующей страницы.
        Упали все — ошибка первой фразы наверх.
        """
        cards: dict[int, SourceCard] = {}
        asked: set[int] = set()  # у кого уже спрашивали название (даже если VK не вернул)
        pending: list[str] = []
        first_error: CollectorError | None = None
        succeeded = 0

        for query in queries:
            try:
                items = await self._search_phrase(query, period)
            except MethodUnavailableError:
                raise  # поиск закрыт ключу целиком: остальные фразы упадут так же
            except CollectorError as exc:
                first_error = first_error or exc
                pending.append(f"Фраза «{query}» не обработана: {exc}")
                continue
            succeeded += 1
            warnings, pending = pending, []
            owners = {int(item["owner_id"]) for item in items} - asked
            asked |= owners
            cards.update(await self._cards_or_empty(owners, warnings))
            posts: list[RawPost] = []
            for item in items:
                owner_id = int(item["owner_id"])
                post = post_from_item(item, cards.get(owner_id) or fallback_card(owner_id))
                if post is not None:
                    posts.append(post)
            yield Page(posts=posts, warnings=warnings)

        if succeeded == 0 and first_error is not None:
            raise first_error
        if pending:
            yield Page(warnings=pending)

    async def _search_phrase(self, query: str, period: Period) -> list[Mapping[str, Any]]:
        """Все страницы newsfeed.search по одной фразе (VK отдаёт не больше ~1000)."""
        params: dict[str, str | int] = {
            "q": query,
            "start_time": int(period.start.timestamp()),
            "end_time": int(period.end.timestamp()),
            "count": SEARCH_PAGE,
        }
        found: list[Mapping[str, Any]] = []
        for _ in range(SEARCH_MAX_PAGES):
            response = await self._api.call("newsfeed.search", **params)
            items = _items(response)
            found.extend(
                item
                for item in items
                if isinstance(item.get("owner_id"), int) and isinstance(item.get("id"), int)
            )
            next_from = response.get("next_from") if isinstance(response, Mapping) else None
            if not items or not next_from:
                break
            params["start_from"] = str(next_from)
        return found

    # ---------- PostReader: открыть пост по ссылке из поисковика (B1-06) ----------

    def accepts(self, url: str) -> bool:
        return wall_ref_from_url(url) is not None

    async def read_post(self, url: str) -> RawPost | None:
        """Пост, который VK отдал по ссылке; удалён / закрыт / не пост — None."""
        ref = wall_ref_from_url(url)
        if ref is None:
            return None
        owner_id, post_id = ref
        response = await self._api.call("wall.getById", posts=f"{owner_id}_{post_id}", extended=1)
        items = response if isinstance(response, list) else _items(response)
        item = next((i for i in items if isinstance(i, Mapping)), None)
        if item is None:
            return None
        cards: dict[int, SourceCard] = {}
        if isinstance(response, Mapping):
            cards.update(card_from_group(g) for g in group_items(response))
            cards.update(card_from_user(u) for u in _list(response.get("profiles")))
        owner = item.get("owner_id")
        card = cards.get(owner) if isinstance(owner, int) else None
        return post_from_item(item, card or fallback_card(owner_id))

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
        if not owner_ids:
            return {}
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


def _list(raw: Any) -> list[Mapping[str, Any]]:
    return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _batches(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]

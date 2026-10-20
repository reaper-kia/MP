"""Ответы VK → типы domain. Чистые функции, без сети: проверяются на fixtures.

Золотое правило: берём только то, что вернул VK. Нет даты — None, нет метрики — None,
нет текста — пост не возвращаем (решает вызывающий). Ссылки строим из id.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from collector_service.domain import messages
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.domain.urls import path_parts
from collector_service.domain.value_objects import PostMetrics, RawPost, SourceInfo

VK_URL = "https://vk.com"

_COMMUNITY_ID = re.compile(r"^(?:club|public|event)(\d+)$")
_PROFILE = re.compile(r"^id\d+$")
_SCREEN_NAME = re.compile(r"^[A-Za-z0-9_.]{2,32}$")
_WALL_POST = re.compile(r"^wall(-?\d+)_(\d+)$")
_VK_HOSTS = frozenset({"vk.com", "vk.ru", "m.vk.com", "m.vk.ru", "www.vk.com", "www.vk.ru"})


@dataclass(frozen=True, slots=True)
class SourceCard:
    """Как подписать пост: название и ссылка источника."""

    name: str
    url: str


def group_ref_from_url(url: str) -> str:
    """Ссылка на сообщество → то, что передаём в groups.getById (числовой id или короткое имя).

    vk.com/krsk_news → "krsk_news";  vk.com/club123, public123, event123 → "123".
    Страница человека (vk.com/id1) — не сообщество: UnsupportedUrlError.
    """
    parts = path_parts(url)
    if len(parts) != 1:
        raise UnsupportedUrlError("Ожидается ссылка вида vk.com/название_сообщества")
    name = parts[0]
    community = _COMMUNITY_ID.match(name)
    if community:
        return community.group(1)
    if _PROFILE.match(name):
        raise UnsupportedUrlError("Это страница человека, а не сообщества ВКонтакте")
    if not _SCREEN_NAME.match(name):
        raise UnsupportedUrlError("Не похоже на ссылку на сообщество ВКонтакте")
    return name


def owner_id_from_external(external_id: str) -> int:
    """source_external_id из ResolveSource: "-12345678" (сообщество) или "1234" (человек)."""
    try:
        owner_id = int(external_id)
    except ValueError:
        raise UnsupportedUrlError(
            messages.source_not_found("ВКонтакте"),
            detail=f"VK: некорректный id источника {external_id!r}",
        ) from None
    if owner_id == 0:
        raise UnsupportedUrlError(
            messages.source_not_found("ВКонтакте"), detail="VK: некорректный id источника 0"
        )
    return owner_id


def group_items(response: Any) -> list[Mapping[str, Any]]:
    """groups.getById: новый формат {"groups": [...]}, старый — просто список."""
    raw = response.get("groups") if isinstance(response, Mapping) else response
    return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def user_items(response: Any) -> list[Mapping[str, Any]]:
    """users.get возвращает список."""
    if not isinstance(response, list):
        return []
    return [item for item in response if isinstance(item, Mapping)]


def source_from_group(item: Mapping[str, Any]) -> SourceInfo:
    group_id = int(item["id"])
    screen_name = _text(item.get("screen_name")) or f"club{group_id}"
    city = item.get("city")
    city_title = _city_title(city.get("title")) if isinstance(city, Mapping) else None
    return SourceInfo(
        platform=Platform.VK,
        external_id=str(-group_id),
        screen_name=screen_name,
        url=f"{VK_URL}/{screen_name}",
        name=_text(item.get("name")) or screen_name,
        city=city_title,
        members_count=_int(item.get("members_count")),
        is_closed=_int(item.get("is_closed")) not in (None, 0),
    )


def card_from_group(item: Mapping[str, Any]) -> tuple[int, SourceCard]:
    group_id = int(item["id"])
    screen_name = _text(item.get("screen_name")) or f"club{group_id}"
    name = _text(item.get("name")) or screen_name
    return -group_id, SourceCard(name=name, url=f"{VK_URL}/{screen_name}")


def card_from_user(item: Mapping[str, Any]) -> tuple[int, SourceCard]:
    user_id = int(item["id"])
    handle = _text(item.get("screen_name")) or f"id{user_id}"
    name = " ".join(
        part for part in (_text(item.get("first_name")), _text(item.get("last_name"))) if part
    )
    return user_id, SourceCard(name=name or handle, url=f"{VK_URL}/{handle}")


def fallback_card(owner_id: int) -> SourceCard:
    """Когда VK не вернул карточку: настоящее короткое имя по id (club123 / id123), не выдумка."""
    handle = f"club{-owner_id}" if owner_id < 0 else f"id{owner_id}"
    return SourceCard(name=handle, url=f"{VK_URL}/{handle}")


def wall_url(owner_id: int, post_id: int) -> str:
    return f"{VK_URL}/wall{owner_id}_{post_id}"


def wall_ref_from_url(url: str) -> tuple[int, int] | None:
    """Ссылка на пост стены → (owner_id, post_id); всё остальное (группы, профили) — None.

    vk.com/wall-68039614_123660, m.vk.ru/wall-1_2, vk.com/krsk?w=wall-1_2 (пост поверх группы).
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _VK_HOSTS:
        return None
    candidates = [parts.path.strip("/")]
    query = parse_qs(parts.query)
    candidates += query.get("w", []) + query.get("z", [])
    for candidate in candidates:
        match = _WALL_POST.match(candidate.split("/")[0])
        if match and int(match.group(1)) != 0:
            return int(match.group(1)), int(match.group(2))
    return None


def post_from_item(item: Mapping[str, Any], card: SourceCard) -> RawPost | None:
    """Пост VK (элемент wall.get или newsfeed.search) → RawPost; без owner_id/id — None.

    text: свой текст + "\\n\\n" + текст оригинала, если это репост. Может получиться пустым —
    такие посты отбрасывает вызывающий и считает в warnings.
    """
    owner_id = _int(item.get("owner_id"))
    post_id = _int(item.get("id"))
    if owner_id is None or post_id is None:
        return None

    history = item.get("copy_history")
    original = history[0] if isinstance(history, list) and history else None
    original = original if isinstance(original, Mapping) else None
    texts = [_text(item.get("text"))]
    if original is not None:
        texts.append(_text(original.get("text")))
    text = "\n\n".join(t for t in texts if t)

    repost_of_url = None
    if original is not None:
        original_owner = _int(original.get("owner_id"))
        original_id = _int(original.get("id"))
        if original_owner is not None and original_id is not None:
            repost_of_url = wall_url(original_owner, original_id)

    date = _int(item.get("date"))
    return RawPost(
        platform=Platform.VK,
        source_external_id=str(owner_id),
        source_name=card.name,
        source_url=card.url,
        post_external_id=str(post_id),
        url=wall_url(owner_id, post_id),
        text=text,
        published_at=datetime.fromtimestamp(date, UTC) if date is not None else None,
        metrics=PostMetrics(
            views=_count(item, "views"),
            likes=_count(item, "likes"),
            reposts=_count(item, "reposts"),
            comments=_count(item, "comments"),
        ),
        is_repost=original is not None,
        repost_of_url=repost_of_url,
    )


def _count(item: Mapping[str, Any], key: str) -> int | None:
    block = item.get(key)
    return _int(block.get("count")) if isinstance(block, Mapping) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _city_title(value: Any) -> str | None:
    """Название города; без единой буквы — None. С токеном пользователя VK ID VK отдаёт вместо
    кириллицы «?4??4??4?…» — такое честнее не показывать, чем показывать мусор."""
    title = _text(value)
    return title if any(ch.isalpha() for ch in title) else None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""

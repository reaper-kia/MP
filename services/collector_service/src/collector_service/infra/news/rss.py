"""RSS 2.0 → элементы ленты. Чистые функции, без сети: проверяются на сохранённых лентах.

Текст берём в порядке полноты: yandex:full-text (ленты для Яндекс.Новостей) → content:encoded →
description. Дата — pubDate (RFC 822); нет или не разобралась — None (не выдумываем).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from collector_service.infra.web.html import strip_html

NS = {
    "yandex": "http://news.yandex.ru",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}


@dataclass(frozen=True, slots=True)
class FeedItem:
    link: str
    guid: str
    title: str
    text: str  # без HTML; может быть коротким анонсом
    full_text: bool  # True — полный текст из ленты, страницу открывать не нужно
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class Feed:
    title: str
    link: str
    items: list[FeedItem]


class FeedError(ValueError):
    pass


def parse_feed(data: bytes | str) -> Feed:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise FeedError(f"лента не разобралась: {exc}") from None
    channel = root.find("channel")
    if channel is None:
        raise FeedError("это не RSS 2.0 (нет <channel>)")
    items = [item for node in channel.iterfind("item") if (item := _item(node)) is not None]
    return Feed(title=_text(channel, "title"), link=_text(channel, "link"), items=items)


def _item(node: Element) -> FeedItem | None:
    link = _text(node, "link")
    if not link:
        return None
    full = _text(node, "yandex:full-text") or _text(node, "content:encoded")
    description = _text(node, "description")
    text = strip_html(full or description)
    return FeedItem(
        link=link,
        guid=_text(node, "guid") or link,
        title=strip_html(_text(node, "title")),
        text=text,
        full_text=bool(full),
        published_at=parse_date(_text(node, "pubDate")),
    )


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return None  # без часового пояса момент неизвестен — не угадываем
    return parsed.astimezone(UTC)


def _text(node: Element, path: str) -> str:
    found = node.find(path, NS)
    if found is None:
        return ""
    return "".join(found.itertext()).strip()

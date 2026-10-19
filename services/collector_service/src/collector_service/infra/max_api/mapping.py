"""Ответы MAX Bot API → типы domain. Чистые функции.

Chat:    chat_id, type ("channel" | "chat" | "dialog"), title, link, participants_count, is_public
Message: timestamp (мс), body {mid, text}, url (публичная ссылка на пост канала), stat {views},
         link {type: "forward", message {text}} — пересланное
Ссылку на пост не строим сами: берём `url` из ответа; нет его — пост не возвращаем.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import PostMetrics, RawPost, SourceInfo

MAX_URL = "https://max.ru"


def source_from_chat(chat: Mapping[str, Any], handle: str) -> SourceInfo:
    link = _text(chat.get("link")) or f"{MAX_URL}/{handle}"
    return SourceInfo(
        platform=Platform.MAX,
        external_id=str(chat["chat_id"]),
        screen_name=handle,
        url=link,
        name=_text(chat.get("title")) or handle,
        members_count=_int(chat.get("participants_count")),
        is_closed=chat.get("is_public") is False,
    )


def post_from_message(
    message: Mapping[str, Any], chat_id: str, source_name: str, source_url: str
) -> RawPost | None:
    body = message.get("body")
    body = body if isinstance(body, Mapping) else {}
    url = _text(message.get("url"))
    mid = _text(body.get("mid")) or _text(body.get("seq"))
    if not url or not mid:
        return None
    texts = [_text(body.get("text"))]
    link = message.get("link")
    forwarded = isinstance(link, Mapping) and link.get("type") == "forward"
    if isinstance(link, Mapping):
        original = link.get("message")
        if isinstance(original, Mapping):
            texts.append(_text(original.get("text")))
    stat = message.get("stat")
    timestamp = _int(message.get("timestamp"))
    return RawPost(
        platform=Platform.MAX,
        source_external_id=chat_id,
        source_name=source_name,
        source_url=source_url,
        post_external_id=mid,
        url=url,
        text="\n\n".join(t for t in texts if t),
        published_at=datetime.fromtimestamp(timestamp / 1000, UTC) if timestamp else None,
        metrics=PostMetrics(views=_int(stat.get("views")) if isinstance(stat, Mapping) else None),
        is_repost=forwarded,
    )


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _text(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value.strip() if isinstance(value, str) else ""

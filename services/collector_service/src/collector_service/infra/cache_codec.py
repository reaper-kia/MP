"""Ответы сервиса ↔ байты для Redis (B2-20): JSON, сжатый zlib, если больше 64 КБ.

Только свои типы (CollectResult, SourceInfo) и только JSON — никакого pickle: значение из Redis
не может выполнить код. Незнакомый формат → ValueError, кэш считает это промахом.
"""

import json
import zlib
from datetime import datetime
from typing import Any

from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import CollectResult, PostMetrics, RawPost, SourceInfo

ZLIB_THRESHOLD = 64 * 1024
_PLAIN = b"j"  # первый байт: j — JSON как есть, z — JSON в zlib
_ZLIB = b"z"


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _post_to_dict(p: RawPost) -> dict[str, Any]:
    return {
        "platform": p.platform.value,
        "source_external_id": p.source_external_id,
        "source_name": p.source_name,
        "source_url": p.source_url,
        "post_external_id": p.post_external_id,
        "url": p.url,
        "text": p.text,
        "title": p.title,
        "published_at": _dt(p.published_at),
        "metrics": [p.metrics.views, p.metrics.likes, p.metrics.reposts, p.metrics.comments],
        "is_repost": p.is_repost,
        "repost_of_url": p.repost_of_url,
        "fetched_at": _dt(p.fetched_at),
    }


def _post_from_dict(d: dict[str, Any]) -> RawPost:
    views, likes, reposts, comments = d["metrics"]
    extra: dict[str, Any] = {}
    fetched_at = _parse_dt(d.get("fetched_at"))
    if fetched_at is not None:
        extra["fetched_at"] = fetched_at
    return RawPost(
        platform=Platform(d["platform"]),
        source_external_id=d["source_external_id"],
        source_name=d["source_name"],
        source_url=d["source_url"],
        post_external_id=d["post_external_id"],
        url=d["url"],
        text=d["text"],
        title=d.get("title"),
        published_at=_parse_dt(d.get("published_at")),
        metrics=PostMetrics(views=views, likes=likes, reposts=reposts, comments=comments),
        is_repost=bool(d.get("is_repost")),
        repost_of_url=d.get("repost_of_url"),
        **extra,
    )


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, CollectResult):
        return {
            "type": "collect",
            "posts": [_post_to_dict(p) for p in value.posts],
            "truncated": value.truncated,
            "warnings": list(value.warnings),
        }
    if isinstance(value, SourceInfo):
        return {
            "type": "source",
            "platform": value.platform.value,
            "external_id": value.external_id,
            "screen_name": value.screen_name,
            "url": value.url,
            "name": value.name,
            "city": value.city,
            "members_count": value.members_count,
            "is_closed": value.is_closed,
        }
    raise TypeError(f"не умеем класть в кэш {type(value).__name__}")


def _from_dict(d: dict[str, Any]) -> CollectResult | SourceInfo:
    kind = d.get("type")
    if kind == "collect":
        return CollectResult(
            posts=[_post_from_dict(p) for p in d["posts"]],
            truncated=bool(d["truncated"]),
            warnings=list(d["warnings"]),
        )
    if kind == "source":
        return SourceInfo(
            platform=Platform(d["platform"]),
            external_id=d["external_id"],
            screen_name=d["screen_name"],
            url=d["url"],
            name=d["name"],
            city=d.get("city"),
            members_count=d.get("members_count"),
            is_closed=bool(d.get("is_closed")),
        )
    raise ValueError(f"незнакомая запись кэша: {kind!r}")


def encode(value: Any) -> bytes:
    raw = json.dumps(_to_dict(value), ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > ZLIB_THRESHOLD:
        return _ZLIB + zlib.compress(raw)
    return _PLAIN + raw


def decode(data: bytes) -> CollectResult | SourceInfo:
    marker, body = data[:1], data[1:]
    if marker == _ZLIB:
        body = zlib.decompress(body)
    elif marker != _PLAIN:
        raise ValueError("незнакомый формат записи кэша")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("запись кэша — не объект")
    return _from_dict(parsed)

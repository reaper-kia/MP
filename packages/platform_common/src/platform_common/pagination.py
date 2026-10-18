"""Непрозрачный курсор поверх offset. Для хакатона достаточно; при желании
замени на keyset (created_at, id) — интерфейс тот же."""

import base64
from dataclasses import dataclass

from platform_common.errors import ValidationError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class Page:
    limit: int
    offset: int

    @classmethod
    def from_request(cls, limit: int, cursor: str) -> "Page":
        limit = DEFAULT_LIMIT if limit <= 0 else min(limit, MAX_LIMIT)
        return cls(limit=limit, offset=decode_cursor(cursor))

    def next_cursor(self, fetched: int) -> str:
        """Передавай fetched = сколько строк вернул запрос с LIMIT limit+1."""
        return encode_cursor(self.offset + self.limit) if fetched > self.limit else ""


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def decode_cursor(cursor: str) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        prefix, value = raw.split(":", 1)
        offset = int(value)
        if prefix != "o" or offset < 0:
            raise ValueError
        return offset
    except ValueError as exc:
        raise ValidationError.field("cursor", "invalid") from exc

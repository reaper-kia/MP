"""Общие части ключей кэша (B2-20)."""

from datetime import UTC

from collector_service.domain.value_objects import Period

_FMT = "%Y-%m-%dT%H:%M:%SZ"


def period_key(period: Period) -> str:
    """Границы периода в UTC до секунды: «2026-10-01T00:00:00Z-2026-10-20T23:59:59Z»."""
    return f"{period.start.astimezone(UTC):{_FMT}}-{period.end.astimezone(UTC):{_FMT}}"

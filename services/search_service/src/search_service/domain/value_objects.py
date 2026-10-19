from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from search_service.domain.errors import SearchInvalidParams
from search_service.domain.enums import Platform

KRASNOYARSK = ZoneInfo("Asia/Krasnoyarsk")

@dataclass(frozen=True, slots=True)
class Period:
    """Даты пользователя YYYY-MM-DD → UTC-границы по Asia/Krasnoyarsk."""
    from_date: date
    to_date: date
    max_days: int = 366

    def __post_init__(self) -> None:
        if self.from_date > self.to_date:
            raise SearchInvalidParams("period_from", "должна быть не позже period_to")
        if (self.to_date - self.from_date).days > self.max_days:
            raise SearchInvalidParams("period", f"не больше {self.max_days} дней")

    @property
    def start_utc(self) -> datetime:
        return datetime.combine(self.from_date, time.min, tzinfo=KRASNOYARSK).astimezone(timezone.utc)

    @property
    def end_utc(self) -> datetime:
        return datetime.combine(self.to_date, time.max, tzinfo=KRASNOYARSK).astimezone(timezone.utc)

    def contains(self, moment: datetime | None) -> bool:
        if moment is None:
            return False
        return self.start_utc <= moment <= self.end_utc


@dataclass(frozen=True, slots=True)
class PostKey:
    """Идентичность публикации: тот же пост из того же источника = та же запись."""
    platform: str
    source_external_id: str
    post_external_id: str
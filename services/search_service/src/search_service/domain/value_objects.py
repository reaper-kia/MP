from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from search_service.domain.errors import SearchInvalidParams
from search_service.domain.exceptions import InvalidPeriodError

KRASNOYARSK = ZoneInfo("Asia/Krasnoyarsk")

# Красноярск — UTC+7 круглый год (без перехода на летнее время с 2014): tzdata не нужна
KRASNOYARSK_TZ = timezone(timedelta(hours=7), name="Asia/Krasnoyarsk")
MAX_PERIOD_DAYS = 366


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
        return datetime.combine(self.from_date, time.min, tzinfo=KRASNOYARSK).astimezone(UTC)

    @property
    def end_utc(self) -> datetime:
        return datetime.combine(self.to_date, time.max, tzinfo=KRASNOYARSK).astimezone(UTC)

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


@dataclass(frozen=True, slots=True)
class UtcPeriod:
    """Период по дате публикации: aware-datetime UTC, обе границы включительно."""

    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end

    @classmethod
    def from_local_dates(cls, date_from: date, date_to: date) -> UtcPeriod:
        """Даты, выбранные пользователем в Красноярске → границы в UTC."""
        if date_from > date_to:
            raise InvalidPeriodError("period_from: должна быть не позже period_to")
        if (date_to - date_from).days >= MAX_PERIOD_DAYS:
            raise InvalidPeriodError(f"period_to: период не длиннее {MAX_PERIOD_DAYS} дней")
        start = datetime.combine(date_from, time.min, KRASNOYARSK_TZ).astimezone(UTC)
        end = datetime.combine(date_to, time.max, KRASNOYARSK_TZ).astimezone(UTC)
        return cls(start=start, end=end)

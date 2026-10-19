from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

from search_service.domain.exceptions import InvalidPeriodError

# Красноярск — UTC+7 круглый год (без перехода на летнее время с 2014): tzdata не нужна
KRASNOYARSK_TZ = timezone(timedelta(hours=7), name="Asia/Krasnoyarsk")
MAX_PERIOD_DAYS = 366


@dataclass(frozen=True, slots=True)
class UtcPeriod:
    """Период по дате публикации: aware-datetime UTC, обе границы включительно."""

    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end

    @classmethod
    def from_local_dates(cls, date_from: date, date_to: date) -> "UtcPeriod":
        """Даты, выбранные пользователем в Красноярске → границы в UTC."""
        if date_from > date_to:
            raise InvalidPeriodError("period_from: должна быть не позже period_to")
        if (date_to - date_from).days >= MAX_PERIOD_DAYS:
            raise InvalidPeriodError(f"period_to: период не длиннее {MAX_PERIOD_DAYS} дней")
        start = datetime.combine(date_from, time.min, KRASNOYARSK_TZ).astimezone(UTC)
        end = datetime.combine(date_to, time.max, KRASNOYARSK_TZ).astimezone(UTC)
        return cls(start=start, end=end)

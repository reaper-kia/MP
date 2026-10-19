"""Даты на страницах OK → момент в UTC.

OK показывает анонимному посетителю время по Москве (проверено: пост, опубликованный на сайте
НГС в 13:12 UTC, в ленте группы OK — «добавлена сегодня в 16:30», т. е. 13:30 UTC = 16:30 МСК).
Форматы, которые встречались в ленте группы:
  «добавлена сегодня в 16:30», «добавлена вчера в 18:46», «добавлена 17 октября в 23:15»;
  для прошлых лет OK добавляет год: «17 октября 2025 в 23:15» (обрабатываем так же).
«сегодня» и «вчера» считаем от момента загрузки страницы по московскому времени.
Только время («16:30» на странице топика) OK пишет для сегодняшних постов — это «сегодня».
Формат незнаком или нет времени — None: дату не выдумываем.
"""

import re
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

OK_TZ = ZoneInfo("Europe/Moscow")

MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}

_RELATIVE = re.compile(r"(сегодня|вчера)\s+(?:в\s+)?(\d{1,2}):(\d{2})")
_ABSOLUTE = re.compile(
    r"(\d{1,2})\s+([а-яё]{3,})\.?\s*(\d{4})?\s*(?:г\.?)?\s*(?:в\s+)?(\d{1,2}):(\d{2})"
)
_TIME_ONLY = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_ok_date(text: str, now: datetime, tz: tzinfo = OK_TZ) -> datetime | None:
    """`now` — aware-момент загрузки страницы. Возвращает aware UTC или None."""
    value = " ".join(text.lower().replace("\xa0", " ").split())
    local_now = now.astimezone(tz)

    if match := _RELATIVE.search(value):
        day = local_now.date() - timedelta(days=1 if match.group(1) == "вчера" else 0)
        return _at(day, int(match.group(2)), int(match.group(3)), tz)

    if match := _ABSOLUTE.search(value):
        day_number, month_word, year, hour, minute = match.groups()
        day_ = _day(int(day_number), month_word, year, local_now.date())
        return _at(day_, int(hour), int(minute), tz) if day_ else None

    if match := _TIME_ONLY.match(value):
        return _at(local_now.date(), int(match.group(1)), int(match.group(2)), tz)
    return None


def _day(day: int, month_word: str, year: str | None, today: date) -> date | None:
    month = MONTHS.get(month_word[:3])
    if month is None:
        return None
    try:
        if year:
            return date(int(year), month, day)
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    # без года OK пишет даты текущего года; «31 декабря» в январе — это прошлый год
    return candidate if candidate <= today else candidate.replace(year=today.year - 1)


def _at(day: date | None, hour: int, minute: int, tz: tzinfo) -> datetime | None:
    if day is None or hour > 23 or minute > 59:
        return None
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz).astimezone(UTC)

"""Перечень новостных сайтов: хост, адрес RSS-ленты, название. Задаётся в настройках
(NEWS_SITES), чтобы менять список без правки кода.

Формат строки: `хост|адрес ленты|Название; хост|адрес ленты|Название; ...`
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsSite:
    host: str
    feed_url: str
    name: str


def parse_sites(value: str) -> list[NewsSite]:
    sites: list[NewsSite] = []
    for chunk in value.split(";"):
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        host = parts[0].lower().removeprefix("www.")
        name = parts[2] if len(parts) > 2 and parts[2] else host
        sites.append(NewsSite(host=host, feed_url=parts[1], name=name))
    return sites

"""Ключ кэша готовой подборки (B2-20).

Одинаковые и похожие запросы по тем же источникам → один ключ. Запрос сводится к набору основ
слов: регистр, «ё», пунктуация, «#» и слитные хэштеги (#КрасноярскийКрай), служебные слова,
порядок слов и окончания не важны — «ДТП в Красноярске», «красноярск, дтп» и «#ДТП #Красноярск»
дают один ключ. Вместо режима и площадок — где поиск реально ищет (coverage): «Мои источники» и
«Везде» по тем же источникам совпадают. Другой период, источник или площадка — другой ключ,
подборки не смешиваются. В ключе — только хэш: текст запроса в Redis и в лог не попадает.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import date

from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import Platform, TargetKind

# v2 — нормализация по основам слов; старые ключи v1 просто перестают попадать
# v3 — ключ по тому, где ищем (источники и поиск по площадке), а не по режиму; старые не попадают
KEY_PREFIX = "mp:search:v3:"
# «такой же поиск уже идёт»: ключ параметров → id поиска, который сейчас собирает подборку
RUNNING_PREFIX = "mp:search:running:v3:"

# служебные слова: на смысл поиска не влияют («не» и «без» меняют смысл — их оставляем)
STOP_WORDS = frozenset(
    "в во на и или а но по о об обо за к ко у с со для из от до при про под над через "
    "же ли бы что как это the a an of in on and or".split()
)
# окончания существительных и прилагательных — от длинных к коротким; основа не короче 3 букв
ENDINGS = tuple(
    sorted(
        "иями ями ами иях ием иям ого его ому ему ыми ими ах ях ам ям ов ев ом ем ой ей ую юю "
        "ая яя ое ее ые ие ый ий ы и а я о е у ю ь й".split(),
        key=len,
        reverse=True,
    )
)
MIN_STEM = 3
_SOFT_TAIL = "аеиоуыэюяйь"  # «движени(е)» и «движен(ие)» → одна основа
_CAMEL = re.compile(r"(?<=[а-яёa-z])(?=[А-ЯЁA-Z])")
_WORD = re.compile(r"[0-9a-zа-я]+")


def _stem(word: str) -> str:
    if len(word) <= MIN_STEM or word.isdigit():
        return word
    stem = word
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= MIN_STEM:
            stem = word[: -len(ending)]
            break
    while len(stem) > MIN_STEM and stem[-1] in _SOFT_TAIL:
        stem = stem[:-1]
    return stem


def normalize_query(query: str) -> str:
    """Запрос → отсортированный набор основ значимых слов (для ключа кэша, не для поиска)."""
    text = _CAMEL.sub(" ", query).lower().replace("ё", "е")
    words = [w for w in _WORD.findall(text) if w not in STOP_WORDS]
    if not words:  # одни служебные слова или символы — хотя бы без лишних пробелов
        return " ".join(query.split()).lower()
    return " ".join(sorted({_stem(w) for w in words}))


def coverage(targets: Iterable[SearchTarget]) -> list[str]:
    """Где поиск реально ищет: источники каталога и поиск по всей площадке.

    Режим («Мои источники» / «Везде») в ключ не входит: «Везде» по тем же источникам — та же
    работа. Поиск по новостным сайтам читает RSS тех же сайтов из перечня, что и источники-сайты
    каталога, поэтому при источниках-сайтах в целях он ничего не добавляет и в ключ не идёт."""
    items = list(targets)
    has_news_sources = any(
        t.kind == TargetKind.SOURCE and t.platform == Platform.NEWS.value for t in items
    )
    out: set[str] = set()
    for t in items:
        if t.kind == TargetKind.SOURCE:
            out.add(f"source:{t.source_id}")
        elif not (t.platform == Platform.NEWS.value and has_news_sources):
            out.add(f"platform:{t.platform}")
    return sorted(out)


def search_cache_key(
    *,
    query: str,
    period_from: date,
    period_to: date,
    targets: Iterable[SearchTarget],
) -> str:
    params = {
        "query": normalize_query(query),
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "where": coverage(targets),
    }
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return KEY_PREFIX + hashlib.sha256(raw.encode()).hexdigest()


def running_key(key: str) -> str:
    """Ключ отметки «идёт» для того же набора параметров."""
    return RUNNING_PREFIX + key.removeprefix(KEY_PREFIX)


def key_of(search: Search) -> str:
    return search_cache_key(
        query=search.query,
        period_from=search.period.from_date,
        period_to=search.period.to_date,
        targets=search.targets,
    )

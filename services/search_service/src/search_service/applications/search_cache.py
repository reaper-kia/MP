"""Ключ кэша готовой подборки (B2-20).

Одинаковые параметры → один ключ: запрос без лишних пробелов и в нижнем регистре, период,
режим, площадки и источники — отсортированы. Другой период, источник или площадка — другой ключ,
подборки не смешиваются. В ключе — только хэш: текст запроса в Redis и в лог не попадает.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import date

from search_service.domain.entities import Search
from search_service.domain.enums import SearchMode

KEY_PREFIX = "mp:search:v1:"


def normalize_query(query: str) -> str:
    return " ".join(query.split()).lower()


def search_cache_key(
    *,
    query: str,
    period_from: date,
    period_to: date,
    mode: SearchMode,
    platforms: Iterable[str],
    source_ids: Iterable[uuid.UUID],
) -> str:
    # в SELECTED площадки берутся из источников (контракт), поэтому в ключе — только источники;
    # в GLOBAL источников нет, только площадки
    selected = mode is SearchMode.SELECTED
    params = {
        "query": normalize_query(query),
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "mode": mode.value,
        "platforms": [] if selected else sorted(set(platforms)),
        "source_ids": sorted({str(s) for s in source_ids}) if selected else [],
    }
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return KEY_PREFIX + hashlib.sha256(raw.encode()).hexdigest()


def key_of(search: Search) -> str:
    return search_cache_key(
        query=search.query,
        period_from=search.period.from_date,
        period_to=search.period.to_date,
        mode=SearchMode(search.mode),
        platforms=search.platforms,
        source_ids=search.source_ids,
    )

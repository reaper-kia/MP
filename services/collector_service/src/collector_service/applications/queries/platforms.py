import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from collector_service.applications.context import RequestContext
from collector_service.applications.mediator import Query
from collector_service.applications.queries.keys import period_key
from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import CollectResult, Period, PlatformInfo


@dataclass(frozen=True)
class GetPlatformsQuery(Query[list[PlatformInfo]]):
    ctx: RequestContext


@dataclass(frozen=True)
class SearchPlatformQuery(Query[CollectResult]):
    """Режим «без ограничения списком»: поиск по всей площадке."""

    ctx: RequestContext
    platform: Platform
    queries: Sequence[str]
    period: Period
    region_terms: Sequence[str] = field(default_factory=list)
    max_posts: int = 0  # 0 — по умолчанию (CollectLimits.per_search)

    def cache_key(self) -> str | None:
        """Поиск по площадке (B2-20): фразы — хэшем (текст запроса в ключ и в лог не попадает),
        порядок и регистр фраз не важны."""
        phrases = sorted({q.strip().lower() for q in self.queries if q.strip()})
        if not phrases:
            return None
        region = sorted({t.strip().lower() for t in self.region_terms if t.strip()})
        digest = hashlib.sha256(
            json.dumps([phrases, region], ensure_ascii=False).encode()
        ).hexdigest()
        return f"mp:psearch:v1:{self.platform}:{digest}:{period_key(self.period)}:{self.max_posts}"

from typing import Any

from pydantic import BaseModel, Field

from gateway.schemas.enums import (
    HEALTH_FROM_PROTO,
    ML_QUERY_TYPE_FROM_PROTO,
    PLATFORM_FROM_PROTO,
    Platform,
    PlatformHealth,
    QueryType,
)


class PlatformInfoOut(BaseModel):
    code: Platform
    title: str
    source_mode: bool = Field(description="Поддерживает поиск по выбранным источникам")
    global_mode: bool = Field(description="Поддерживает поиск по всей площадке")
    status: PlatformHealth
    note: str | None

    @classmethod
    def from_proto(cls, p: Any) -> "PlatformInfoOut":
        return cls(
            code=PLATFORM_FROM_PROTO[p.platform],
            title=p.title,
            source_mode=p.source_mode_supported,
            global_mode=p.global_mode_supported,
            status=HEALTH_FROM_PROTO.get(p.health, "unavailable"),
            note=p.note or None,
        )


class QueryAnalyzeIn(BaseModel):
    query: str = Field(min_length=3, max_length=20000)


class QueryAnalysisOut(BaseModel):
    query_type: QueryType | None  # null — ML не определил тип (упрощённый режим)
    summary: str
    search_queries: list[str]
    needs_clarification: bool
    clarification_hint: str | None

    @classmethod
    def from_proto(
        cls, a: Any, query_type_map: dict[int, QueryType] | None = None
    ) -> "QueryAnalysisOut":
        mapping = query_type_map or ML_QUERY_TYPE_FROM_PROTO
        return cls(
            query_type=mapping.get(a.query_type),
            summary=a.summary,
            search_queries=list(a.search_queries),
            needs_clarification=a.needs_clarification,
            clarification_hint=a.clarification_hint or None,
        )

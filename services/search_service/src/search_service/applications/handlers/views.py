"""Сущности домена (B2) → read models (то, что transport/grpc/mappers.py кладёт в proto)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from search_service.applications.handlers.save import make_title
from search_service.applications.ports.collector_client import SourceInfo
from search_service.applications.results.read_models import (
    ErrorInfoView,
    ExcerptPartView,
    MetricsView,
    QueryAnalysisView,
    RegionView,
    ResultSourceView,
    ResultView,
    SearchCacheView,
    SearchCountsView,
    SearchParamsView,
    SearchProgressView,
    SearchTargetView,
    SearchView,
    SourcePreviewView,
    SourceView,
)
from search_service.domain.entities import Publication, Search, SearchResult, SearchTarget, Source
from search_service.domain.enums import (
    Platform,
    QueryType,
    Relevance,
    SearchMode,
    Sentiment,
    TargetKind,
    TitleSource,
)

EXCERPT_FALLBACK_LEN = 300


def _query_type(value: object) -> QueryType | None:
    try:
        return QueryType(str(value))
    except ValueError:
        return None


# ───────────────────────── источники ─────────────────────────


def source_view(s: Source) -> SourceView:
    return SourceView(
        id=s.id,
        platform=Platform(s.platform),
        external_id=s.external_id,
        url=s.url,
        name=s.name,
        city=s.city,
        is_regional=s.is_regional,
        is_active=s.is_active,
        notes=s.notes,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def preview_view(info: SourceInfo, existing: Source | None) -> SourcePreviewView:
    return SourcePreviewView(
        platform=Platform(info.platform),
        external_id=info.external_id,
        url=info.url,
        name=info.name or info.screen_name,
        city=info.city,
        members_count=info.members_count,
        existing_source_id=existing.id if existing else None,
    )


# ───────────────────────── поиск ─────────────────────────


def counts_view(counts: dict[str, int]) -> SearchCountsView:
    return SearchCountsView(**{k: int(v) for k, v in counts.items()})


def target_view(t: SearchTarget) -> SearchTargetView:
    error = (
        ErrorInfoView(code=t.error_code, message=t.error_message or t.error_code)
        if t.error_code
        else None
    )
    return SearchTargetView(
        id=t.id,
        kind=TargetKind(t.kind),
        platform=Platform(t.platform),
        source_id=t.source_id,
        name=t.name,
        url=t.url,
        status=t.status,
        fetched=t.fetched,
        matched=t.matched,
        error=error,
        attempts=t.attempts,
        finished_at=t.finished_at,
    )


def analysis_view(qa: dict[str, Any] | None) -> QueryAnalysisView | None:
    if not qa:
        return None
    return QueryAnalysisView(
        query_type=_query_type(qa.get("query_type")) or QueryType.TOPIC,
        summary=str(qa.get("summary", "")),
        search_queries=[str(q) for q in qa.get("search_queries", [])],
        needs_clarification=bool(qa.get("needs_clarification", False)),
        clarification_hint=str(qa.get("clarification_hint", "")),
    )


def search_view(s: Search, counts: SearchCountsView, *, with_targets: bool = True) -> SearchView:
    total, finished, percent = s.progress()
    return SearchView(
        id=s.id,
        status=s.status,
        stage=s.stage,
        progress=SearchProgressView(
            targets_total=total, targets_finished=finished, percent=percent
        ),
        params=SearchParamsView(
            query=s.query,
            query_type=_query_type(s.query_type),
            period_from=s.period.from_date,
            period_to=s.period.to_date,
            mode=SearchMode(s.mode),
            platforms=[Platform(p) for p in s.platforms],
            source_ids=list(s.source_ids),
        ),
        query_analysis=analysis_view(s.query_analysis),
        targets=[target_view(t) for t in s.targets] if with_targets else [],
        counts=counts,
        warnings=list(s.warnings),
        created_at=s.created_at,
        started_at=s.started_at,
        finished_at=s.finished_at,
        cache=(
            SearchCacheView(
                from_search_id=s.cached_from_search_id,
                created_at=s.cached_at or s.created_at,
            )
            if s.cached_from_search_id is not None
            else None
        ),
    )


# ───────────────────────── подборка ─────────────────────────


def excerpt_parts(
    text: str, start: int, end: int, highlights: Iterable[list[int]]
) -> list[ExcerptPartView]:
    """Выдержка text[start:end], порезанная на куски; склейка кусков = выдержка."""
    spans: list[tuple[int, int]] = []
    for span in highlights:
        if len(span) != 2:
            continue
        a, b = max(span[0], start), min(span[1], end)
        if a < b:
            spans.append((a, b))
    spans.sort()
    parts: list[ExcerptPartView] = []
    pos = start
    for a, b in spans:
        a = max(a, pos)  # пересекающиеся подсветки склеиваем
        if a >= b:
            continue
        if a > pos:
            parts.append(ExcerptPartView(text=text[pos:a], highlight=False))
        parts.append(ExcerptPartView(text=text[a:b], highlight=True))
        pos = b
    if pos < end:
        parts.append(ExcerptPartView(text=text[pos:end], highlight=False))
    return parts


def _metrics(metrics: dict[str, int] | None) -> MetricsView:
    m = metrics or {}
    return MetricsView(
        views=m.get("views"),
        likes=m.get("likes"),
        reposts=m.get("reposts"),
        comments=m.get("comments"),
    )


def _sentiment(value: str | None) -> Sentiment | None:
    try:
        return Sentiment(value) if value else None
    except ValueError:
        return None


def result_view(
    r: SearchResult, pub: Publication, catalog_source: Source | None, group_size: int
) -> ResultView:
    title, title_source = make_title(pub)
    if r.excerpt_start is not None and r.excerpt_end is not None:
        start, end = r.excerpt_start, r.excerpt_end
    else:
        start, end = 0, min(EXCERPT_FALLBACK_LEN, len(pub.text))
    return ResultView(
        id=r.id,
        publication_id=pub.id,
        platform=Platform(pub.platform),
        source=ResultSourceView(
            source_id=catalog_source.id if catalog_source else None,
            name=catalog_source.name if catalog_source else pub.source_name,
            url=catalog_source.url if catalog_source else pub.source_url,
            is_regional=r.region_by_source,
        ),
        url=pub.url,
        title=title,
        title_source=TitleSource(title_source),
        excerpt=pub.text[start:end],
        excerpt_parts=excerpt_parts(pub.text, start, end, r.highlights),
        published_at=pub.published_at,
        date_status=r.date_status,
        relevance=r.relevance or Relevance.DISPUTED,
        score=r.score or 0.0,
        explanation=r.explanation,
        region=RegionView(
            by_source=r.region_by_source,
            by_content=r.region_by_content,
            evidence=r.region_evidence,
        ),
        sentiment=_sentiment(r.sentiment),
        group_id=r.group_id,
        group_size=group_size,
        metrics=_metrics(pub.metrics),
        excluded=r.excluded,
        found_by_target_id=r.target_id,
    )

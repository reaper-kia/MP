"""Разбор запроса. Сейчас — эвристика ML-01 (degraded); ML-03 — LLM с тем же результатом."""

from ml_service.core.models import QueryAnalysis, QueryType
from ml_service.core.text import sentences, stems

NEWS_TEXT_MIN_CHARS = 300
NEWS_TEXT_MIN_SENTENCES = 3


def detect_query_type(query: str) -> QueryType:
    text = query.strip()
    if len(text) > NEWS_TEXT_MIN_CHARS or len(list(sentences(text))) >= NEWS_TEXT_MIN_SENTENCES:
        return QueryType.NEWS_TEXT
    return QueryType.TOPIC


def analyze_query_heuristic(query: str) -> QueryAnalysis:
    text = " ".join(query.split())
    query_type = detect_query_type(text)
    meaningful = stems(text)
    if query_type is QueryType.NEWS_TEXT:
        first = next(iter(sentences(query)), (0, min(len(query), 120)))
        title = query[first[0] : first[1]].strip()[:120]
        return QueryAnalysis(
            query_type=query_type,
            summary=f"Текст новости: «{title}» — ищем её размещения",
            search_queries=[title],
        )
    return QueryAnalysis(
        query_type=query_type,
        summary=f"Тема: {text}",
        search_queries=[text],
        needs_clarification=len(meaningful) < 2,
        clarification_hint=(
            "Уточните запрос: добавьте, о чём именно (например, «дорожная безопасность»)"
            if len(meaningful) < 2
            else ""
        ),
    )

"""Оценка связи постов с запросом.

ML-01 (сейчас): пересечение основ слов → класс по порогам. Сомнение → DISPUTED (recall важнее).
ML-04: эмбеддинги + леммы; ML-05: LLM-судья. Сигнатура score_posts_heuristic остаётся образцом.
"""

from ml_service.core.excerpt import best_excerpt, highlight_spans
from ml_service.core.models import Post, PostScore, QueryAnalysis, Relevance
from ml_service.core.region import find_region
from ml_service.core.text import stems

DIRECT_AT = 0.5
INDIRECT_AT = 0.25
DISPUTED_AT = 0.1


def query_stems(query: str, analysis: QueryAnalysis) -> set[str]:
    parts = [query, *analysis.search_queries, *analysis.must_concepts]
    result: set[str] = set()
    for part in parts:
        result |= stems(part)
    return result


def score_post_heuristic(post: Post, q_stems: set[str], exclude: set[str]) -> PostScore:
    text_stems = stems(f"{post.title or ''} {post.text}")
    common = q_stems & text_stems
    score = len(common) / len(q_stems) if q_stems else 0.0
    if exclude and exclude <= text_stems and score < DIRECT_AT:
        score = 0.0  # явно о другом (например, «пожарная безопасность»)

    if score >= DIRECT_AT:
        relevance = Relevance.DIRECT
    elif score >= INDIRECT_AT:
        relevance = Relevance.INDIRECT
    elif score >= DISPUTED_AT:
        relevance = Relevance.DISPUTED
    else:
        relevance = Relevance.IRRELEVANT

    excerpt = best_excerpt(post.text, q_stems)
    region = find_region(post.text)
    explanation = (
        f"Упрощённая проверка: совпало {len(common)} ключевых слов из {len(q_stems)}"
        if common
        else "Упрощённая проверка: ключевые слова запроса не найдены"
    )
    return PostScore(
        id=post.id,
        relevance=relevance,
        score=round(min(score, 1.0), 3),
        explanation=explanation,
        region_by_content=bool(region),
        region_evidence=region,
        sentiment=None,  # без модели тональность не определяем — не выдумываем
        excerpt_span=excerpt,
        highlight_spans=highlight_spans(post.text, q_stems, within=excerpt),
    )


def score_posts_heuristic(
    query: str, analysis: QueryAnalysis, posts: list[Post]
) -> list[PostScore]:
    q_stems = query_stems(query, analysis)
    exclude: set[str] = set()
    for concept in analysis.exclude_concepts:
        exclude |= stems(concept)
    return [score_post_heuristic(p, q_stems, exclude) for p in posts]

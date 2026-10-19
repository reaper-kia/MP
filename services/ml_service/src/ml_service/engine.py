"""MlEngine — что вызывает транспорт. Выбирает путь (модель или эвристика) и следит за контрактом.

Правило: сервис не падает из-за модели. Модель недоступна / ответила мусором → эвристика + degraded.
"""

import logging

from ml_service.core.grouping import group_posts_heuristic
from ml_service.core.models import GroupInput, Post, PostGroup, PostScore, QueryAnalysis, Span
from ml_service.core.query import analyze_query_heuristic
from ml_service.core.scoring import score_posts_heuristic
from ml_service.errors import InvalidRequestError
from ml_service.providers.embeddings import Embedder
from ml_service.providers.llm import LLM

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 20_000
MAX_EXCERPT = 300


class MlEngine:
    def __init__(self, llm: LLM, embedder: Embedder, max_posts_per_call: int) -> None:
        self._llm = llm
        self._embedder = embedder
        self._max_posts = max_posts_per_call

    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]:
        text = query.strip()
        if len(text) < 3 or len(text) > MAX_QUERY_CHARS:
            raise InvalidRequestError("Запрос должен быть от 3 до 20000 символов")
        # TODO(ML-03): if self._llm.available: try LLM-разбор, при ошибке — эвристика ниже
        return analyze_query_heuristic(text), True

    async def score_posts(
        self, query: str, analysis: QueryAnalysis, posts: list[Post]
    ) -> tuple[list[PostScore], bool]:
        if len(posts) > self._max_posts:
            raise InvalidRequestError(f"Не больше {self._max_posts} постов за вызов")
        if len({p.id for p in posts}) != len(posts):
            raise InvalidRequestError("id постов должны быть уникальны")
        # TODO(ML-04/05/06): эмбеддинги → LLM-судья; для NEWS_TEXT — same_news
        scores = score_posts_heuristic(query, analysis, posts)
        return [_checked(s, p) for s, p in zip(scores, posts, strict=True)], True

    async def group_posts(self, posts: list[GroupInput]) -> list[PostGroup]:
        # TODO(ML-07): MinHash + эмбеддинги
        return group_posts_heuristic(posts)


def _checked(score: PostScore, post: Post) -> PostScore:
    """Страховка контракта: span'ы внутри текста, выдержка ≤ 300."""
    n = len(post.text)

    def ok(span: Span) -> bool:
        return 0 <= span.start < span.end <= n

    excerpt = score.excerpt_span
    if not ok(excerpt) or excerpt.end - excerpt.start > MAX_EXCERPT:
        logger.warning("bad excerpt span for %s: %s", post.id, excerpt)
        excerpt = Span(0, min(n, MAX_EXCERPT)) if n else Span(0, 0)
    highlights = [h for h in score.highlight_spans if ok(h)]
    if excerpt is score.excerpt_span and len(highlights) == len(score.highlight_spans):
        return score
    return PostScore(
        id=score.id,
        relevance=score.relevance,
        score=score.score,
        explanation=score.explanation,
        region_by_content=score.region_by_content,
        region_evidence=score.region_evidence,
        sentiment=score.sentiment,
        excerpt_span=excerpt,
        highlight_spans=highlights,
    )

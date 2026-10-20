"""MlEngine — что вызывает транспорт. Выбирает путь (модель или эвристика) и следит за контрактом.

Правило: сервис не падает из-за модели. Модель недоступна / ответила мусором / не успела в бюджет
→ эвристика + degraded. Бюджеты меньше таймаутов search_service, чтобы ответ успел дойти.

degraded:
- AnalyzeQuery — разбор сделала эвристика, а не LLM;
- ScorePosts — хотя бы один пост оценён без модели (ни эмбеддингов, ни LLM-судьи).
"""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

from ml_service.core.grouping import group_posts_heuristic
from ml_service.core.judge import JudgeCache, JudgeStats, Verdict, judge_posts
from ml_service.core.llm_json import LlmAnswerError
from ml_service.core.models import (
    GroupInput,
    Post,
    PostGroup,
    PostScore,
    QueryAnalysis,
    QueryType,
    Relevance,
    Span,
)
from ml_service.core.query import analyze_query_heuristic, analyze_query_llm
from ml_service.core.same_news import score_news_posts
from ml_service.core.scoring import (
    V1Result,
    banded,
    post_text,
    score_posts_v1,
    semantic,
    short_sentence,
)
from ml_service.errors import InvalidRequestError, MlUnavailableError
from ml_service.providers.base import LLM, Embedder

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 20_000
MAX_EXCERPT = 300
MAX_EMBED_CHARS = 2_000
ORDER = [Relevance.IRRELEVANT, Relevance.DISPUTED, Relevance.INDIRECT, Relevance.DIRECT]
QUERY_CACHE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class EngineLimits:
    max_posts_per_call: int = 50
    max_group_posts: int = 500
    analyze_budget: float = 15.0
    score_budget: float = 45.0
    group_budget: float = 40.0
    judge_batch_size: int = 6
    judge_concurrency: int = 2
    judge_max_post_chars: int = 1200


class MlEngine:
    def __init__(
        self,
        llm: LLM,
        embedder: Embedder,
        max_posts_per_call: int = 50,
        *,
        judge_llm: LLM | None = None,
        limits: EngineLimits | None = None,
    ) -> None:
        self._llm = llm
        self._judge = judge_llm or llm
        self._embedder = embedder
        self._limits = limits or EngineLimits(max_posts_per_call=max_posts_per_call)
        self._judge_cache = JudgeCache()
        self._query_cache: OrderedDict[str, QueryAnalysis] = OrderedDict()
        self.last_judge_stats = JudgeStats()
        self.last_similarities: list[float] | None = None  # для eval --details

    @property
    def describe(self) -> str:
        return f"llm={self._llm.name}, judge={self._judge.name}, embeddings={self._embedder.name}"

    async def embeddings_ready(self) -> bool:
        if not self._embedder.available:
            return False
        await self._embedder.embed(["проверка"], "query")
        return True

    async def aclose(self) -> None:
        for provider in {id(p): p for p in (self._llm, self._judge, self._embedder)}.values():
            await provider.aclose()

    # ───────────────────────── AnalyzeQuery ─────────────────────────

    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]:
        text = query.strip()
        if len(text) < 3 or len(text) > MAX_QUERY_CHARS:
            raise InvalidRequestError("Запрос должен быть от 3 до 20000 символов")

        # Кэш разбора по тексту запроса (ML-13)
        cache_key = text.lower()
        if cache_key in self._query_cache:
            self._query_cache.move_to_end(cache_key)
            return self._query_cache[cache_key], False

        base = analyze_query_heuristic(text)
        if not self._llm.available:
            return base, True
        try:
            analysis = await asyncio.wait_for(
                analyze_query_llm(self._llm, text, base), self._limits.analyze_budget
            )
        except (MlUnavailableError, LlmAnswerError, TimeoutError) as e:
            logger.warning("AnalyzeQuery: LLM не ответила по делу (%s) — эвристика", _short(e))
            return base, True

        self._query_cache[cache_key] = analysis
        if len(self._query_cache) > QUERY_CACHE_SIZE:
            self._query_cache.popitem(last=False)

        return analysis, False

    # ───────────────────────── ScorePosts ─────────────────────────

    async def score_posts(
        self, query: str, analysis: QueryAnalysis, posts: list[Post]
    ) -> tuple[list[PostScore], bool]:
        if len(posts) > self._limits.max_posts_per_call:
            raise InvalidRequestError(
                f"Не больше {self._limits.max_posts_per_call} постов за вызов"
            )
        if len({p.id for p in posts}) != len(posts):
            raise InvalidRequestError("id постов должны быть уникальны")
        if not posts:
            return [], False
        deadline = time.monotonic() + self._limits.score_budget

        similarities = await self._similarities(query, analysis, posts, deadline)
        self.last_similarities = similarities
        if analysis.query_type is QueryType.NEWS_TEXT:
            v1 = score_news_posts(query, posts, similarities)
        else:
            v1 = score_posts_v1(query, analysis, posts, similarities)

        verdicts: dict[str, Verdict] = {}
        stats = JudgeStats()
        if self._judge.available:
            raw = {p.id: r.raw for p, r in zip(posts, v1, strict=True)}
            candidates = [p for p, r in zip(posts, v1, strict=True) if _worth_judging(r)]
            # не успеем всех — пусть модель первой увидит самые вероятные
            candidates.sort(key=lambda p: -raw[p.id])
            verdicts = await judge_posts(
                self._judge,
                query,
                analysis,
                candidates,
                cache=self._judge_cache,
                batch_size=self._limits.judge_batch_size,
                concurrency=self._limits.judge_concurrency,
                max_post_chars=self._limits.judge_max_post_chars,
                deadline=deadline,
                stats=stats,
            )
        self.last_judge_stats = stats

        scores = []
        by_model = True
        for post, result in zip(posts, v1, strict=True):
            verdict = verdicts.get(post.id)
            if verdict is not None:
                scores.append(_checked(_merge(result, verdict), post))
            else:
                # v1 без эмбеддингов и без судьи = чистая эвристика
                by_model = by_model and result.similarity is not None
                scores.append(_checked(result.score, post))
        if stats.sent or stats.cached:
            logger.info(
                "ScorePosts: %d постов, судья %d (+%d из кэша), без судьи %d, вызовов %d",
                len(posts),
                stats.sent,
                stats.cached,
                stats.failed,
                stats.calls,
            )
        return scores, not by_model

    async def _similarities(
        self, query: str, analysis: QueryAnalysis, posts: list[Post], deadline: float
    ) -> list[float] | None:
        if not self._embedder.available:
            return None
        if analysis.query_type is QueryType.NEWS_TEXT:
            query_text = query[:MAX_EMBED_CHARS]
        else:
            parts = [query, analysis.summary, *analysis.must_concepts]
            query_text = ". ".join(p for p in parts if p)
        try:
            vectors = await asyncio.wait_for(
                self._embed_all(query_text, [post_text(p) for p in posts]),
                max(1.0, (deadline - time.monotonic()) * 0.4),
            )
        except (MlUnavailableError, TimeoutError) as e:
            logger.warning("ScorePosts: эмбеддинги недоступны (%s) — только лексика", _short(e))
            return None
        q, docs = vectors
        return [sum(a * b for a, b in zip(q, d, strict=True)) for d in docs]

    async def _embed_all(
        self, query_text: str, docs: list[str]
    ) -> tuple[list[float], list[list[float]]]:
        q = await self._embedder.embed([query_text], "query")
        d = await self._embedder.embed([t[:MAX_EMBED_CHARS] for t in docs], "doc")
        return q[0], d

    # ───────────────────────── GroupPosts ─────────────────────────

    async def group_posts(self, posts: list[GroupInput]) -> list[PostGroup]:
        if len(posts) > self._limits.max_group_posts:
            raise InvalidRequestError(f"Не больше {self._limits.max_group_posts} постов за вызов")
        if len({p.id for p in posts}) != len(posts):
            raise InvalidRequestError("id постов должны быть уникальны")
        vectors: list[list[float]] | None = None
        if self._embedder.available and len(posts) > 1:
            texts = [
                (f"{p.title}\n{p.text}" if p.title else p.text)[:MAX_EMBED_CHARS] for p in posts
            ]
            try:
                vectors = await asyncio.wait_for(
                    self._embedder.embed(texts, "doc"), self._limits.group_budget * 0.6
                )
            except (MlUnavailableError, TimeoutError) as e:
                logger.warning(
                    "GroupPosts: эмбеддинги недоступны (%s) — только по словам", _short(e)
                )
        # чистый CPU: уводим в поток, чтобы не блокировать event loop gRPC
        return await asyncio.to_thread(group_posts_heuristic, posts, vectors)


def _short(e: BaseException) -> str:
    return (str(e) or type(e).__name__)[:200]


def _worth_judging(result: V1Result) -> bool:
    """В модель не отправляем только явно мимо: по смыслу ниже нижнего порога (SIM_LOW) и ни одного
    общего слова. Низкий порог — экономим время, полноту не теряем. Без эмбеддингов — судят все.
    """
    if result.similarity is None or result.person_missing:
        return True
    return result.lexical > 0 or semantic(result.similarity) > 0


def _merge(result: V1Result, verdict: Verdict) -> PostScore:
    """Класс и объяснение от судьи, позиции и регион — от v1. Резкое расхождение → DISPUTED."""
    relevance = verdict.relevance
    v1 = result.score.relevance
    gap = ORDER.index(v1) - ORDER.index(relevance)
    explanation = verdict.explanation or result.score.explanation
    if gap >= 3:
        # v1 уверен «прямая», модель — «мимо»: полнота важнее, отдаём человеку
        relevance = Relevance.DISPUTED
    if result.conflict and relevance is Relevance.DIRECT:
        # модель говорит «та же новость», а место / дата / цифры расходятся
        relevance = Relevance.DISPUTED
        explanation = short_sentence(f"Модель считает новость той же, но {result.conflict}")
    if result.person_missing and relevance in {Relevance.DIRECT, Relevance.INDIRECT}:
        relevance = Relevance.DISPUTED
        explanation = short_sentence(
            f"{explanation.rstrip('.…')}; {result.person_missing} не назван — проверьте"
        )
    return PostScore(
        id=result.score.id,
        relevance=relevance,
        score=banded(relevance, result.raw),
        explanation=explanation,
        region_by_content=result.score.region_by_content,
        region_evidence=result.score.region_evidence,
        sentiment=verdict.sentiment,
        excerpt_span=result.score.excerpt_span,
        highlight_spans=result.score.highlight_spans,
    )


def _checked(score: PostScore, post: Post) -> PostScore:
    """Страховка контракта: span'ы внутри текста, выдержка ≤ 300, score 0..1, объяснение ≤ 150."""
    n = len(post.text)

    def ok(span: Span) -> bool:
        return 0 <= span.start < span.end <= n

    excerpt = score.excerpt_span
    if not ok(excerpt) or excerpt.end - excerpt.start > MAX_EXCERPT:
        logger.warning("bad excerpt span for %s: %s", post.id, excerpt)
        excerpt = Span(0, min(n, MAX_EXCERPT)) if n else Span(0, 0)
    highlights = [h for h in score.highlight_spans if ok(h)]
    explanation = short_sentence(score.explanation) or "Оценка без объяснения"
    value = min(1.0, max(0.0, score.score))
    if (
        excerpt is score.excerpt_span
        and len(highlights) == len(score.highlight_spans)
        and explanation == score.explanation
        and value == score.score
    ):
        return score
    return PostScore(
        id=score.id,
        relevance=score.relevance,
        score=value,
        explanation=explanation,
        region_by_content=score.region_by_content,
        region_evidence=score.region_evidence,
        sentiment=score.sentiment,
        excerpt_span=excerpt,
        highlight_spans=highlights,
    )

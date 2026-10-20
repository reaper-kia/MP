"""Оценка связи постов с запросом — v1 (ML-04): лексика + эмбеддинги + справочник края.

Это быстрый слой: он даёт оценку КАЖДОМУ посту (и фолбэк, если LLM-судья не успел), выдержку,
подсветку и регион. LLM-судья (judge.py) потом уточняет класс, объяснение и тональность.
Сомнение → DISPUTED: полнота важнее, человек проверит.
"""

from dataclasses import dataclass

from ml_service.core.excerpt import best_excerpt, highlight_spans
from ml_service.core.models import Post, PostScore, QueryAnalysis, QueryType, Relevance
from ml_service.core.region import REGION_STEMS, find_region
from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.core.text import stems, tokens

# Классы по итоговому скору 0..1 (подобраны на eval/, см. eval/report.md)
DIRECT_AT = 0.55
INDIRECT_AT = 0.35
DISPUTED_AT = 0.15

# Пороги косинуса «запрос ↔ пост» — у эмбеддера (core/similarity.py, свои у каждой модели)
SEMANTIC_WEIGHT = 0.6

# Итоговый score в ответе — внутри полосы своего класса: сортировка «класс → score» не ломается
BANDS: dict[Relevance, tuple[float, float]] = {
    Relevance.DIRECT: (0.75, 1.0),
    Relevance.INDIRECT: (0.5, 0.75),
    Relevance.DISPUTED: (0.25, 0.5),
    Relevance.IRRELEVANT: (0.0, 0.25),
}
MAX_EXPLANATION = 150


@dataclass(frozen=True, slots=True)
class QueryContext:
    query_type: QueryType
    phrases: list[set[str]]  # основы каждой фразы запроса без региональных слов
    all_stems: set[str]  # всё, что подсвечиваем и по чему ищем выдержку
    exclude: list[tuple[str, set[str]]]  # (понятие, его основы) — «пожарная безопасность»
    person_stems: list[tuple[str, str]]  # (фамилия, основа) — для запроса о человеке


@dataclass(frozen=True, slots=True)
class V1Result:
    score: PostScore  # готовый ответ v1 (класс, объяснение, выдержка, регион)
    raw: float  # 0..1 до раскладки по полосам
    lexical: float
    similarity: float | None
    exclude_hit: str
    person_missing: str
    conflict: str = ""  # «та же новость»: расходятся место / дата / цифры


def build_context(query: str, analysis: QueryAnalysis) -> QueryContext:
    sources = [query, *analysis.search_queries, *analysis.must_concepts]
    phrases = [s for s in (stems(p) - REGION_STEMS for p in sources) if s]
    if not phrases:
        # запрос целиком из названий края («Красноярск»): тогда регион и есть тема
        phrases = [s for s in (stems(p) for p in sources) if s]
    all_stems: set[str] = set()
    for p in sources:
        all_stems |= stems(p)
    persons: list[tuple[str, str]] = []
    if analysis.query_type is QueryType.PERSON:
        for concept in analysis.must_concepts:
            for t in tokens(concept):
                if t.text[:1].isupper():
                    persons.append((t.text, t.stem))
    return QueryContext(
        query_type=analysis.query_type,
        phrases=phrases,
        all_stems=all_stems,
        exclude=[(c, stems(c)) for c in analysis.exclude_concepts if stems(c)],
        person_stems=persons,
    )


def semantic(similarity: float, thresholds: SimilarityThresholds = BGE_M3) -> float:
    return thresholds.semantic(similarity)


def relevance_for(raw: float) -> Relevance:
    if raw >= DIRECT_AT:
        return Relevance.DIRECT
    if raw >= INDIRECT_AT:
        return Relevance.INDIRECT
    if raw >= DISPUTED_AT:
        return Relevance.DISPUTED
    return Relevance.IRRELEVANT


def banded(relevance: Relevance, raw: float) -> float:
    lo, hi = BANDS[relevance]
    return round(lo + (hi - lo) * min(1.0, max(0.0, raw)) * 0.999, 3)


def short_sentence(text: str, limit: int = MAX_EXPLANATION) -> str:
    """Одно предложение ≤ limit символов по границе слова."""
    text = " ".join(text.split())
    for mark in (". ", "! ", "? "):
        if mark in text:
            text = text[: text.index(mark) + 1]
            break
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    return (cut[: cut.rfind(" ")] if " " in cut else cut).rstrip(",;:—- ") + "…"


def post_text(post: Post) -> str:
    """Текст поста для сравнения и эмбеддингов: заголовок (если есть) + текст."""
    return f"{post.title}\n{post.text}" if post.title else post.text


def score_post_v1(
    post: Post,
    ctx: QueryContext,
    similarity: float | None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> V1Result:
    full = post_text(post)
    text_stems = stems(full)

    lexical = max((len(p & text_stems) / len(p) for p in ctx.phrases), default=0.0)
    if similarity is None:
        raw = lexical
    else:
        raw = SEMANTIC_WEIGHT * thresholds.semantic(similarity) + (1 - SEMANTIC_WEIGHT) * lexical

    exclude_hit = next((c for c, s in ctx.exclude if s <= text_stems), "")
    if exclude_hit:
        raw *= 0.3  # «пожарная безопасность» при запросе о дорожной — почти наверняка мимо

    person_missing = ""
    if ctx.person_stems and not any(s in text_stems for _, s in ctx.person_stems):
        person_missing = ctx.person_stems[-1][0]
        raw = min(raw, DISPUTED_AT - 0.01)

    relevance = relevance_for(raw)
    excerpt = best_excerpt(post.text, ctx.all_stems)
    region = find_region(post.text)
    explanation = _explain(
        full,
        ctx,
        similarity,
        thresholds,
        exclude_hit=exclude_hit,
        person_missing=person_missing,
    )
    score = PostScore(
        id=post.id,
        relevance=relevance,
        score=banded(relevance, raw),
        explanation=explanation,
        region_by_content=bool(region),
        region_evidence=region,
        sentiment=None,  # без модели тональность не определяем — не выдумываем
        excerpt_span=excerpt,
        highlight_spans=highlight_spans(post.text, ctx.all_stems, within=excerpt),
    )
    return V1Result(score, raw, lexical, similarity, exclude_hit, person_missing)


def _explain(
    text: str,
    ctx: QueryContext,
    similarity: float | None,
    thresholds: SimilarityThresholds,
    *,
    exclude_hit: str,
    person_missing: str,
) -> str:
    prefix = "Упрощённая проверка" if similarity is None else "Автоматическая оценка"
    if person_missing:
        return short_sentence(f"{prefix}: {person_missing} в посте не упоминается")
    if exclude_hit:
        return short_sentence(f"{prefix}: похоже, пост о другом — «{exclude_hit}»")
    topic_stems = set().union(*ctx.phrases) if ctx.phrases else set()
    words: list[str] = []
    for t in tokens(text):
        if t.stem in topic_stems and t.text.lower() not in {w.lower() for w in words}:
            words.append(t.text)
        if len(words) == 3:
            break
    parts = []
    if words:
        parts.append("есть " + ", ".join(f"«{w}»" for w in words))
    if similarity is not None:
        sem = thresholds.semantic(similarity)
        parts.append(
            "по смыслу близко к запросу"
            if sem >= 0.6
            else "по смыслу частично связано"
            if sem >= 0.3
            else "по смыслу далеко от запроса"
        )
    if not parts:
        parts.append("ключевые слова запроса не найдены")
    return short_sentence(f"{prefix}: " + "; ".join(parts))


def score_posts_v1(
    query: str,
    analysis: QueryAnalysis,
    posts: list[Post],
    similarities: list[float] | None = None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> list[V1Result]:
    ctx = build_context(query, analysis)
    sims: list[float | None] = list(similarities) if similarities else [None] * len(posts)
    return [score_post_v1(p, ctx, s, thresholds) for p, s in zip(posts, sims, strict=True)]


def score_posts_heuristic(
    query: str, analysis: QueryAnalysis, posts: list[Post]
) -> list[PostScore]:
    """Без моделей — образец сигнатуры, им пользуются тесты и eval."""
    return [r.score for r in score_posts_v1(query, analysis, posts)]

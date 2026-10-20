"""Режим «текст новости» (сценарий 2, ML-06): копия / сокращение / пересказ → DIRECT;
похожая новость о ДРУГОМ событии → IRRELEVANT с объяснением.

Сигналы: общие основы слов (доля от меньшего текста), вложенность шинглов (копия, сокращение),
близость эмбеддингов (пересказ) и факты — место, дата, числа с единицами («3 часа», «10 млн»).
Расхождение фактов — главный признак «похожее, но другое событие». Фиксированного процента
совпадения нет (так и в ТЗ): решение по совокупности, сомнение → DISPUTED.
"""

from dataclasses import dataclass

from ml_service.core.excerpt import best_excerpt, highlight_spans
from ml_service.core.models import Post, PostScore, Relevance
from ml_service.core.region import REGION_STEMS, find_region, places
from ml_service.core.scoring import V1Result, banded, post_text, short_sentence
from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.core.text import MONTHS, dates, overlap, quantities, shingles, stems, word_stems

MONTH_STEMS = frozenset(m[:6] for m in MONTHS)
SAME_AT = 0.5  # доля общих основ: дальше — та же новость (если факты не спорят)
MAYBE_AT = 0.3
COPY_CONTAINMENT = 0.8
SHORT_CONTAINMENT = 0.45
# доля общих основ считается от меньшего текста: у «Сегодня понедельник, 19 октября» одно общее
# слово уже даёт треть — без нескольких общих основ похожесть по словам не засчитываем
MIN_SHARED_WORDS = 4


@dataclass(frozen=True, slots=True)
class NewsFacts:
    words: set[str]
    shingles: set[tuple[str, ...]]
    places: set[str]
    dates: set[tuple[int, int]]
    quantities: dict[str, set[str]]
    length: int

    @classmethod
    def of(cls, text: str) -> "NewsFacts":
        return cls(
            words={
                s for s in word_stems(text) if s not in REGION_STEMS and s[:6] not in MONTH_STEMS
            },
            shingles=shingles(text),
            places=places(text),
            dates=dates(text),
            quantities=quantities(text),
            length=len(text),
        )


@dataclass(frozen=True, slots=True)
class Comparison:
    word_overlap: float
    containment: float  # доля шинглов поста, найденных в исходнике
    conflicts: list[str]
    anchors: int  # совпавшие факты: место, дата, числа


def compare(source: NewsFacts, post: NewsFacts) -> Comparison:
    conflicts: list[str] = []
    anchors = 0
    if source.places and post.places:
        if source.places & post.places:
            anchors += 1
        else:
            conflicts.append("другое место (" + ", ".join(sorted(post.places))[:40] + ")")
    if source.dates and post.dates:
        if source.dates & post.dates:
            anchors += 1
        else:
            day, month = sorted(post.dates)[0]
            conflicts.append(f"другая дата ({day:02d}.{month:02d})")
    for unit in source.quantities.keys() & post.quantities.keys():
        if source.quantities[unit] & post.quantities[unit]:
            anchors += 1
        else:
            theirs, ours = sorted(post.quantities[unit])[0], sorted(source.quantities[unit])[0]
            conflicts.append(f"другие цифры ({theirs} вместо {ours})")
    contained = len(post.shingles & source.shingles) / len(post.shingles) if post.shingles else 0.0
    return Comparison(overlap(source.words, post.words), contained, conflicts, anchors)


def score_news_post(
    post: Post,
    source: NewsFacts,
    source_stems: set[str],
    similarity: float | None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> V1Result:
    facts = NewsFacts.of(post_text(post))
    cmp = compare(source, facts)
    signal = cmp.word_overlap if len(source.words & facts.words) >= MIN_SHARED_WORDS else 0.0
    if similarity is not None:
        signal = max(signal, thresholds.semantic(similarity) * 0.9)
        if similarity >= thresholds.same_news:  # пересказ: порог у эмбеддера
            signal = max(signal, SAME_AT)

    if cmp.conflicts and cmp.containment < COPY_CONTAINMENT:
        relevance = Relevance.IRRELEVANT
        raw = 0.2 * signal
        explanation = "Похожая новость, но другое событие: " + ", ".join(cmp.conflicts[:2])
    elif (
        cmp.containment >= COPY_CONTAINMENT
        or signal >= SAME_AT
        or (signal >= MAYBE_AT + 0.05 and cmp.anchors >= 2)
    ):
        relevance = Relevance.DIRECT
        raw = max(signal, cmp.containment)
        explanation = _kind(cmp, facts, source)
    elif signal >= MAYBE_AT or (cmp.anchors >= 2 and signal >= 0.15):
        relevance = Relevance.DISPUTED
        raw = signal
        explanation = "Возможно, та же новость: часть деталей совпадает — проверьте"
    else:
        relevance = Relevance.IRRELEVANT
        raw = signal
        explanation = "Другая новость: общих деталей с исходным текстом мало"

    excerpt = best_excerpt(post.text, source_stems)
    region = find_region(post.text)
    score = PostScore(
        id=post.id,
        relevance=relevance,
        score=banded(relevance, raw),
        explanation=short_sentence(explanation),
        region_by_content=bool(region),
        region_evidence=region,
        sentiment=None,
        excerpt_span=excerpt,
        highlight_spans=highlight_spans(post.text, source_stems, within=excerpt),
    )
    conflict = ", ".join(cmp.conflicts[:2])
    return V1Result(score, raw, cmp.word_overlap, similarity, "", "", conflict)


def _kind(cmp: Comparison, post: NewsFacts, source: NewsFacts) -> str:
    if cmp.containment >= COPY_CONTAINMENT and post.length >= source.length * 0.8:
        return "Та же новость: копия исходного текста"
    shorter = post.length < source.length * 0.9
    if shorter and (cmp.containment >= SHORT_CONTAINMENT or cmp.word_overlap >= 0.85):
        return "Та же новость в сокращении"
    details = []
    if source.places & post.places:
        details.append("место")
    if source.dates & post.dates:
        details.append("дата")
    shared_units = source.quantities.keys() & post.quantities.keys()
    if any(source.quantities[u] & post.quantities[u] for u in shared_units):
        details.append("цифры")
    tail = f": совпадают {', '.join(details)}" if details else ""
    return f"Та же новость в пересказе{tail}"


def score_news_posts(
    source_text: str,
    posts: list[Post],
    similarities: list[float] | None = None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> list[V1Result]:
    source = NewsFacts.of(source_text)
    source_stems = stems(source_text)
    sims: list[float | None] = list(similarities) if similarities else [None] * len(posts)
    return [
        score_news_post(p, source, source_stems, s, thresholds)
        for p, s in zip(posts, sims, strict=True)
    ]


def facts_conflict(a: str, b: str) -> bool:
    """Для группировки: у двух текстов спорят место, дата или числа — это разные события."""
    return bool(compare(NewsFacts.of(a), NewsFacts.of(b)).conflicts)

"""Группы одинаковых новостей (сюжеты), ML-07.

Пара постов — одна новость, если:
- почти дубли: шинглы (тройки основ) пересекаются по Жаккару ≥ 0.5 или короткий пост на ≥ 70 %
  вложен в длинный (сокращённая копия);
- пересказ: общих основ много (доля от меньшего ≥ 0.5) или эмбеддинги близки
  (косинус ≥ порога retell эмбеддера, который посчитал векторы);
- и при этом факты не спорят: место, дата, числа (иначе это похожая, но другая новость).
«Пересказ по словам» требует ещё и не меньше MIN_SHARED_WORDS общих основ: короткий пост
(«Дорожная обстановка в Солнечном») делит половину своих слов с любой новостью про дороги.

Группы — не связные компоненты (цепочка «метро ~ перекрытие ~ ДТП» склеивала десятки разных
новостей в одну), а жадная кластеризация: пост входит в группу, только если совпадает с её
первым постом и хотя бы с половиной её постов (проверяем до CHECK_MEMBERS первых).
Каждый пост ровно в одной группе; одиночки — группа из одного. Перед сравнением — дешёвый
отсев по общим словам: 500 постов (лимит контракта) — до 125 тыс. пар, это секунды на чистом
Python; косинус — только для прошедших отсев.
"""

from collections.abc import Sequence

from ml_service.core.models import GroupInput, PostGroup
from ml_service.core.same_news import NewsFacts, compare
from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.core.text import jaccard, overlap

SHINGLE_JACCARD = 0.5
CONTAINMENT = 0.7
WORD_OVERLAP = 0.5
SIM_MIN_OVERLAP = 0.25  # даже при близких эмбеддингах нужно немного общих слов
MIN_SHARED_WORDS = 6  # пересказ «по словам» — не меньше стольких общих основ
CHECK_MEMBERS = 12  # с каким числом постов группы сверяем кандидата


def _text(p: GroupInput) -> str:
    return f"{p.title}\n{p.text}" if p.title else p.text


def same_story(
    a: NewsFacts,
    b: NewsFacts,
    similarity: float | None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> bool:
    shingle_j = jaccard(a.shingles, b.shingles)
    small, big = (a, b) if len(a.shingles) <= len(b.shingles) else (b, a)
    contained = len(small.shingles & big.shingles) / len(small.shingles) if small.shingles else 0.0
    near_duplicate = shingle_j >= SHINGLE_JACCARD or (
        contained >= CONTAINMENT and len(small.shingles) >= 4
    )
    words = overlap(a.words, b.words)
    shared = len(a.words & b.words)
    retelling = (words >= WORD_OVERLAP and shared >= MIN_SHARED_WORDS) or (
        similarity is not None and similarity >= thresholds.retell and words >= SIM_MIN_OVERLAP
    )
    if not (near_duplicate or retelling):
        return False
    # почти дубль с другими цифрами всё равно другое событие («пожар … 2 часа» и «… 3 часа»)
    return not compare(small, big).conflicts


def group_posts_heuristic(
    posts: list[GroupInput],
    vectors: Sequence[list[float]] | None = None,
    thresholds: SimilarityThresholds = BGE_M3,
) -> list[PostGroup]:
    facts = [NewsFacts.of(_text(p)) for p in posts]
    pairs: dict[tuple[int, int], bool] = {}

    def same(i: int, j: int) -> bool:
        key = (i, j) if i < j else (j, i)
        if key not in pairs:
            ok = overlap(facts[i].words, facts[j].words) >= SIM_MIN_OVERLAP
            if ok:
                sim = None
                if vectors is not None:
                    sim = sum(x * y for x, y in zip(vectors[i], vectors[j], strict=True))
                ok = same_story(facts[i], facts[j], sim, thresholds)
            pairs[key] = ok
        return pairs[key]

    clusters: list[list[int]] = []
    for i in range(len(posts)):
        best, best_share = -1, 0.0
        for c, members in enumerate(clusters):
            sample = members[:CHECK_MEMBERS]
            hits = sum(1 for j in sample if same(i, j))
            share = hits / len(sample)
            # с первым постом группы — обязательно: иначе группа «ползёт» от сюжета к сюжету
            if same(i, members[0]) and hits * 2 >= len(sample) and share > best_share:
                best, best_share = c, share
        if best < 0:
            clusters.append([i])
        else:
            clusters[best].append(i)
    buckets = {n: members for n, members in enumerate(clusters)}

    groups = []
    for n, members in enumerate(buckets.values(), start=1):
        # представитель — с заголовком площадки, иначе самый полный текст
        rep = max(members, key=lambda i: (posts[i].title is not None, len(posts[i].text)))
        groups.append(
            PostGroup(
                group_id=f"g{n}",
                post_ids=[posts[i].id for i in members],
                representative_post_id=posts[rep].id,
            )
        )
    return groups

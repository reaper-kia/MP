"""Группы одинаковых новостей (сюжеты), ML-07.

Пара постов — одна новость, если:
- почти дубли: шинглы (тройки основ) пересекаются по Жаккару ≥ 0.5 или короткий пост на ≥ 70 %
  вложен в длинный (сокращённая копия);
- пересказ: общих основ много (доля от меньшего ≥ 0.5) или эмбеддинги близки (косинус ≥ 0.86);
- и при этом факты не спорят: место, дата, числа (иначе это похожая, но другая новость).
Группы — связные компоненты. Каждый пост ровно в одной группе; одиночки — группа из одного.
Сравниваем все пары, но сначала дешёвый отсев по общим словам: 500 постов (лимит контракта) —
125 тыс. пар, это секунды на чистом Python; косинус считаем только для прошедших отсев.
"""

from collections.abc import Sequence

from ml_service.core.models import GroupInput, PostGroup
from ml_service.core.same_news import NewsFacts, compare
from ml_service.core.text import jaccard, overlap

SHINGLE_JACCARD = 0.5
CONTAINMENT = 0.7
WORD_OVERLAP = 0.5
SIM_RETELL = 0.86
SIM_MIN_OVERLAP = 0.25  # даже при близких эмбеддингах нужно немного общих слов


def _text(p: GroupInput) -> str:
    return f"{p.title}\n{p.text}" if p.title else p.text


def same_story(a: NewsFacts, b: NewsFacts, similarity: float | None) -> bool:
    shingle_j = jaccard(a.shingles, b.shingles)
    small, big = (a, b) if len(a.shingles) <= len(b.shingles) else (b, a)
    contained = len(small.shingles & big.shingles) / len(small.shingles) if small.shingles else 0.0
    near_duplicate = shingle_j >= SHINGLE_JACCARD or (
        contained >= CONTAINMENT and len(small.shingles) >= 4
    )
    words = overlap(a.words, b.words)
    retelling = words >= WORD_OVERLAP or (
        similarity is not None and similarity >= SIM_RETELL and words >= SIM_MIN_OVERLAP
    )
    if not (near_duplicate or retelling):
        return False
    # почти дубль с другими цифрами всё равно другое событие («пожар … 2 часа» и «… 3 часа»)
    return not compare(small, big).conflicts


def group_posts_heuristic(
    posts: list[GroupInput], vectors: Sequence[list[float]] | None = None
) -> list[PostGroup]:
    facts = [NewsFacts.of(_text(p)) for p in posts]
    parent = list(range(len(posts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            if find(i) == find(j) or overlap(facts[i].words, facts[j].words) < SIM_MIN_OVERLAP:
                continue
            sim = None
            if vectors is not None:
                sim = sum(x * y for x, y in zip(vectors[i], vectors[j], strict=True))
            if same_story(facts[i], facts[j], sim):
                parent[find(j)] = find(i)

    buckets: dict[int, list[int]] = {}
    for i in range(len(posts)):
        buckets.setdefault(find(i), []).append(i)

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

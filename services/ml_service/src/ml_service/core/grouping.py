"""Группы одинаковых новостей.

ML-01 (сейчас): сходство Жаккара по основам слов ≥ порога → одна группа (связные компоненты).
ML-07: MinHash для почти-дублей + эмбеддинги для пересказов.
"""

from ml_service.core.models import GroupInput, PostGroup
from ml_service.core.text import stems

SAME_NEWS_JACCARD = 0.7


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def group_posts_heuristic(posts: list[GroupInput]) -> list[PostGroup]:
    parent = list(range(len(posts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    words = [stems(f"{p.title or ''} {p.text}") for p in posts]
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            if jaccard(words[i], words[j]) >= SAME_NEWS_JACCARD:
                parent[find(j)] = find(i)

    buckets: dict[int, list[GroupInput]] = {}
    for i, post in enumerate(posts):
        buckets.setdefault(find(i), []).append(post)

    groups = []
    for n, members in enumerate(buckets.values(), start=1):
        representative = max(members, key=lambda p: len(p.text))
        groups.append(
            PostGroup(
                group_id=f"g{n}",
                post_ids=[p.id for p in members],
                representative_post_id=representative.id,
            )
        )
    return groups

"""Пороги косинусной близости эмбеддингов.

У каждой модели эмбеддингов своё распределение косинусов, а векторы разных моделей несравнимы:
пороги — свойство провайдера (`Embedder.thresholds`), а не глобальная константа. Значения по
умолчанию подобраны для bge-m3 (eval/); для Яндекса их задают настройки `SIM_*_YANDEX`.
Движок берёт пороги того эмбеддера, который посчитал векторы этого вызова.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimilarityThresholds:
    # «запрос ↔ пост»: ниже low — точно не о том, выше high — точно о том
    low: float = 0.38
    high: float = 0.68
    # «пост ↔ пост»: пересказ одной новости (GroupPosts)
    retell: float = 0.86
    # «исходная новость ↔ пост» (сценарий 2): выше — пересказ той же новости
    same_news: float = 0.85

    def __post_init__(self) -> None:
        if not 0 <= self.low < self.high <= 1:
            raise ValueError(f"неверные пороги близости: low={self.low}, high={self.high}")
        if not (0 < self.retell <= 1 and 0 < self.same_news <= 1):
            raise ValueError(
                f"неверные пороги близости: retell={self.retell}, same_news={self.same_news}"
            )

    def semantic(self, similarity: float) -> float:
        """Косинус → 0..1: 0 ниже low, 1 выше high, линейно между."""
        return min(1.0, max(0.0, (similarity - self.low) / (self.high - self.low)))


# bge-m3 (Ollama): подобраны на eval/, см. eval/report.md
BGE_M3 = SimilarityThresholds()

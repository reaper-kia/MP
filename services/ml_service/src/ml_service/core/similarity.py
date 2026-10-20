"""Пороги косинусной близости эмбеддингов. У каждой модели эмбеддингов своё распределение
косинусов: значения по умолчанию подобраны для bge-m3 (eval/), для других моделей их задают
настройки (`SIM_LOW`, `SIM_HIGH`, `SIM_RETELL`) — composition root вызывает configure() при старте.
"""

from dataclasses import dataclass


@dataclass
class SimilarityThresholds:
    # «запрос ↔ пост»: ниже low — точно не о том, выше high — точно о том
    low: float = 0.38
    high: float = 0.68
    # «пост ↔ пост»: пересказ одной новости (GroupPosts)
    retell: float = 0.86


THRESHOLDS = SimilarityThresholds()


def configure(low: float, high: float, retell: float) -> None:
    if not 0 <= low < high <= 1 or not 0 < retell <= 1:
        raise ValueError(f"неверные пороги близости: low={low}, high={high}, retell={retell}")
    THRESHOLDS.low = low
    THRESHOLDS.high = high
    THRESHOLDS.retell = retell

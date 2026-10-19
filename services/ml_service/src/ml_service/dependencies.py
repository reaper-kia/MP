"""Composition root: настройки → провайдеры → MlEngine."""

from ml_service.config import Settings
from ml_service.engine import MlEngine
from ml_service.providers.embeddings import build_embedder
from ml_service.providers.llm import build_llm


def build_engine(settings: Settings) -> MlEngine:
    return MlEngine(
        llm=build_llm(settings),
        embedder=build_embedder(settings),
        max_posts_per_call=settings.max_posts_per_call,
    )

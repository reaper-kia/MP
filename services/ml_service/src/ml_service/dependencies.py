"""Composition root: настройки → провайдеры → MlEngine. Не бросает: нет модели — эвристики."""

import asyncio
import logging

from ml_service.config import Settings
from ml_service.engine import EngineLimits, MlEngine
from ml_service.errors import MlUnavailableError
from ml_service.providers.embeddings import build_embedder
from ml_service.providers.llm import build_judge_llm, build_llm

logger = logging.getLogger(__name__)


def build_engine(settings: Settings) -> MlEngine:
    llm = build_llm(settings)
    return MlEngine(
        llm=llm,
        embedder=build_embedder(settings),
        judge_llm=build_judge_llm(settings, llm),
        limits=EngineLimits(
            max_posts_per_call=settings.max_posts_per_call,
            max_group_posts=settings.max_group_posts,
            analyze_budget=settings.analyze_budget_seconds,
            score_budget=settings.score_budget_seconds,
            group_budget=settings.group_budget_seconds,
            judge_batch_size=settings.judge_batch_size,
            judge_concurrency=settings.judge_concurrency,
            judge_max_post_chars=settings.judge_max_post_chars,
        ),
    )


async def warm_up(engine: MlEngine) -> None:
    """Пробный запрос к моделям: загружает их в память Ollama и пишет в лог, что работает.

    Модель не отвечает — сервис всё равно работает (эвристики), в логе — почему.
    """
    try:
        _, degraded = await engine.analyze_query("Безопасность дорожного движения")
        logger.info("Прогрев LLM: %s", "эвристика (degraded)" if degraded else "модель отвечает")
    except Exception as e:  # прогрев не должен ронять сервис ни при каких ошибках
        logger.warning("Прогрев LLM не удался: %s", e)
    try:
        ok = await engine.embeddings_ready()
        logger.info("Прогрев эмбеддингов: %s", "модель отвечает" if ok else "не подключены")
    except (MlUnavailableError, TimeoutError, asyncio.CancelledError) as e:
        logger.warning("Прогрев эмбеддингов не удался: %s", e)

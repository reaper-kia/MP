from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["stub", "ollama", "yandex"]


class Settings(BaseSettings):
    grpc_address: str = "[::]:50055"

    # stub — без моделей: эвристики, все ответы с degraded=true.
    # ollama — локальные модели (основной режим команды). yandex — не реализован: сервис стартует,
    # пишет в лог причину и работает на эвристиках (degraded=true).
    llm_provider: Provider = "stub"
    embed_provider: Provider = "stub"

    # Yandex AI Studio — оставлено под будущий провайдер, сейчас не используется
    yc_folder_id: str = ""
    yc_api_key: str = ""

    # Ollama (docker compose --profile llm-local up -d ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:7b-instruct"
    # судья ScorePosts; пусто — та же модель. Если не укладывается в 60 с на батч — взять поменьше
    ollama_judge_model: str = ""
    ollama_embed_model: str = "bge-m3"
    ollama_keep_alive: str = "30m"  # держать модель в памяти между запросами
    ollama_num_ctx: int = 8192

    # таймауты одного запроса к модели
    llm_timeout_seconds: float = 40.0
    embed_timeout_seconds: float = 30.0
    # после сбоя модель не дёргаем столько секунд (сразу эвристика), потом пробуем снова
    breaker_cooldown_seconds: float = 30.0

    # бюджеты на весь RPC — меньше таймаутов search_service (AnalyzeQuery 20 с, ScorePosts и
    # GroupPosts 60 с), чтобы успеть отдать хотя бы эвристику, а не упасть по таймауту
    analyze_budget_seconds: float = 15.0
    score_budget_seconds: float = 45.0
    group_budget_seconds: float = 40.0

    # LLM-судья: постов в одном промпте и одновременных промптов на один вызов ScorePosts
    judge_batch_size: int = 6
    judge_concurrency: int = 2
    judge_max_post_chars: int = 1200

    embed_batch_size: int = 32

    max_posts_per_call: int = 50
    max_group_posts: int = 500

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

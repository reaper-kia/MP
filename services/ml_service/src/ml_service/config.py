from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["stub", "ollama", "yandex"]


class Settings(BaseSettings):
    grpc_address: str = "[::]:50055"

    # stub — без моделей: эвристики, все ответы с degraded=true
    llm_provider: Provider = "stub"
    embed_provider: Provider = "stub"

    # Yandex AI Studio (имена моделей сверить с документацией, ML-03)
    yc_folder_id: str = ""
    yc_api_key: str = ""
    yandex_llm_model: str = "yandexgpt-lite"
    yandex_embed_query_model: str = "text-search-query"
    yandex_embed_doc_model: str = "text-search-doc"

    # Ollama (docker compose --profile llm-local up)
    ollama_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:7b-instruct"
    ollama_embed_model: str = "bge-m3"

    llm_timeout_seconds: float = 30.0
    max_posts_per_call: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

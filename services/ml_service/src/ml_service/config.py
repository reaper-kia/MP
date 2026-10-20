from functools import lru_cache
from typing import Literal, cast

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "yandex"]
PROVIDERS: tuple[str, ...] = ("stub", "ollama", "yandex")


def parse_chain(value: str, variable: str) -> list[Provider]:
    """«ollama,yandex» → ["ollama", "yandex"]. stub — конец цепочки (он и так всегда последний
    неявно), поэтому «stub» → []. Неизвестное имя — ValueError: сервис не стартует с опечаткой.
    """
    chain: list[Provider] = []
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    for i, name in enumerate(names):
        if name not in PROVIDERS:
            raise ValueError(
                f"{variable}: неизвестный провайдер «{name}», допустимо: {', '.join(PROVIDERS)} "
                "(несколько — через запятую по порядку, например ollama,yandex)"
            )
        if name == "stub":
            if i != len(names) - 1:
                raise ValueError(f"{variable}: stub — только последним (это эвристики)")
            break
        if name not in chain:
            chain.append(cast(Provider, name))
    return chain


class Settings(BaseSettings):
    grpc_address: str = "[::]:50055"
    # HTTP /health для нас (какой провайдер сейчас активен); пусто — не поднимать
    health_address: str = "0.0.0.0:8085"

    # Провайдеры по порядку, через запятую: «ollama,yandex» — сначала Ollama (ноут через туннель),
    # не отвечает — Yandex AI Studio, нет и его — эвристики (stub, всегда последний неявно).
    # Один провайдер (stub / ollama / yandex) — как раньше.
    # stub — без моделей: эвристики, все ответы с degraded=true.
    # Без ключа / модели сервис всё равно стартует: причина в логе, ответы эвристикой.
    # Вариант «без LLM»: LLM_PROVIDER=stub, EMBED_PROVIDER=yandex — отбор по эмбеддингам и словам.
    llm_provider: str = "stub"
    # пусто — та же цепочка, что у LLM_PROVIDER
    embed_provider: str = ""

    # Yandex AI Studio (Foundation Models API): API-ключ сервисного аккаунта с ролью
    # ai.languageModels.user на каталоге YC_FOLDER_ID
    yc_folder_id: str = ""
    yc_api_key: str = ""
    yc_api_url: str = "https://ai.api.cloud.yandex.net"
    yc_llm_model: str = "yandexgpt-lite/latest"
    # судья ScorePosts; пусто — та же модель (например yandexgpt/latest — точнее, дороже)
    yc_judge_model: str = ""
    yc_embed_doc_model: str = "text-search-doc/latest"
    yc_embed_query_model: str = "text-search-query/latest"
    yc_embed_concurrency: int = 8  # textEmbedding — один текст на запрос
    yc_retries: int = 2  # повторы на 429 / 5xx

    # Пороги косинуса эмбеддингов (core/similarity.py) — у каждого провайдера свои, векторы
    # разных моделей несравнимы. SIM_* — Ollama (bge-m3, подобраны на eval), SIM_*_YANDEX — Яндекс
    # (до калибровки ML-11 те же; подобрать: `eval/run_eval.py --details` печатает косинусы)
    sim_low: float = 0.38
    sim_high: float = 0.68
    sim_retell: float = 0.86
    sim_same_news: float = 0.85
    sim_low_yandex: float = 0.38
    sim_high_yandex: float = 0.68
    sim_retell_yandex: float = 0.86
    sim_same_news_yandex: float = 0.85

    # Ollama (docker compose --profile llm-local up -d ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:7b-instruct"
    # судья ScorePosts; пусто — та же модель. Если не укладывается в 60 с на батч — взять поменьше
    ollama_judge_model: str = ""
    ollama_embed_model: str = "bge-m3"
    ollama_keep_alive: str = "30m"  # держать модель в памяти между запросами
    ollama_num_ctx: int = 8192
    # Ollama на ноуте через SSH-туннель: ноут уснул / без сети — понять это за секунды, а не за
    # таймаут запроса. Подключение — не дольше connect-таймаута; если ответа от Ollama не было
    # дольше OLLAMA_PROBE_AFTER_SECONDS, перед запросом быстрый GET /api/version (туннель может
    # принять соединение и молчать). 0 — без проверки.
    ollama_connect_timeout_seconds: float = 3.0
    ollama_probe_after_seconds: float = 20.0

    # таймауты одного запроса к модели
    llm_timeout_seconds: float = 40.0
    embed_timeout_seconds: float = 30.0
    # после сбоя модель не дёргаем столько секунд (сразу эвристика), потом пробуем снова
    breaker_cooldown_seconds: float = 30.0

    # бюджеты на весь RPC — меньше таймаутов search_service (AnalyzeQuery 25 с, ScorePosts и
    # GroupPosts 60 с), чтобы успеть отдать хотя бы эвристику, а не упасть по таймауту
    analyze_budget_seconds: float = 20.0
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

    @field_validator("llm_provider", "embed_provider")
    @classmethod
    def _check_chain(cls, value: str, info: ValidationInfo) -> str:
        parse_chain(value, (info.field_name or "").upper())
        return value.strip().lower()

    @property
    def llm_chain(self) -> list[Provider]:
        return parse_chain(self.llm_provider, "LLM_PROVIDER")

    @property
    def embed_chain(self) -> list[Provider]:
        if not self.embed_provider.strip():
            return self.llm_chain
        return parse_chain(self.embed_provider, "EMBED_PROVIDER")


@lru_cache
def get_settings() -> Settings:
    return Settings()

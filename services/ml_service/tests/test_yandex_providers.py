"""Провайдеры Yandex AI Studio на поддельном HTTP-транспорте + сборка по настройкам."""

import json

import httpx
import pytest

from ml_service.config import Settings
from ml_service.core.similarity import SimilarityThresholds
from ml_service.errors import MlUnavailableError
from ml_service.providers import yandex
from ml_service.providers.embeddings import StubEmbedder, build_embedder
from ml_service.providers.fallback import FallbackEmbedder
from ml_service.providers.llm import StubLLM, build_llm
from ml_service.providers.yandex import YandexClient, YandexEmbedder, YandexLLM

COMPLETION_OK = {
    "result": {
        "alternatives": [
            {
                "message": {"role": "assistant", "text": '{"query_type": "topic"}'},
                "status": "ALTERNATIVE_STATUS_FINAL",
            }
        ],
        "usage": {"inputTextTokens": "10", "completionTokens": "5", "totalTokens": "15"},
        "modelVersion": "x",
    }
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(yandex, "_pause", instant)


def client_with(handler: httpx.MockTransport, retries: int = 2) -> YandexClient:
    return YandexClient(
        "https://ai.api.cloud.yandex.net",
        "KEY",
        "b1gfolder",
        timeout=1,
        retries=retries,
        transport=handler,
    )


async def test_completion_request_and_json_text() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/foundationModels/v1/completion"
        assert request.headers["Authorization"] == "Api-Key KEY"
        assert request.headers["x-folder-id"] == "b1gfolder"
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=COMPLETION_OK)

    llm = YandexLLM(client_with(httpx.MockTransport(handle)), "yandexgpt-lite/latest", cooldown=60)
    assert await llm.complete_json("sys", "user", max_tokens=300) == '{"query_type": "topic"}'
    assert seen["modelUri"] == "gpt://b1gfolder/yandexgpt-lite/latest"
    assert seen["jsonObject"] is True
    options = seen["completionOptions"]
    assert isinstance(options, dict)
    assert options["maxTokens"] == "300" and options["temperature"] == 0
    messages = seen["messages"]
    assert isinstance(messages, list)
    assert [m["role"] for m in messages] == ["system", "user"]
    await llm.aclose()


async def test_rate_limit_is_retried() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="too many requests")
        return httpx.Response(200, json=COMPLETION_OK)

    llm = YandexLLM(client_with(httpx.MockTransport(handle)), "yandexgpt-lite/latest", cooldown=60)
    assert await llm.complete_json("sys", "user")
    assert calls == 2 and llm.available
    await llm.aclose()


async def test_bad_key_opens_breaker_with_clear_reason() -> None:
    llm = YandexLLM(
        client_with(httpx.MockTransport(lambda r: httpx.Response(403, text="denied"))),
        "yandexgpt-lite/latest",
        cooldown=60,
    )
    with pytest.raises(MlUnavailableError, match="ключ не принят"):
        await llm.complete_json("sys", "user")
    assert not llm.available  # дальше сразу эвристика
    await llm.aclose()


async def test_content_filter_does_not_open_breaker() -> None:
    filtered = {
        "result": {
            "alternatives": [
                {
                    "message": {"role": "assistant", "text": "…"},
                    "status": "ALTERNATIVE_STATUS_CONTENT_FILTER",
                }
            ]
        }
    }
    llm = YandexLLM(
        client_with(httpx.MockTransport(lambda r: httpx.Response(200, json=filtered))),
        "yandexgpt-lite/latest",
        cooldown=60,
    )
    with pytest.raises(MlUnavailableError, match="фильтром"):
        await llm.complete_json("sys", "user")
    assert llm.available  # про конкретный текст, а не про модель
    await llm.aclose()


async def test_embeddings_query_vs_doc_normalized_and_cached() -> None:
    uris: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/foundationModels/v1/textEmbedding"
        body = json.loads(request.content)
        uris.append(body["modelUri"])
        return httpx.Response(200, json={"embedding": [3.0, 4.0], "numTokens": "2"})

    emb = YandexEmbedder(
        client_with(httpx.MockTransport(handle)),
        doc_model="text-search-doc/latest",
        query_model="text-search-query/latest",
        concurrency=4,
        cooldown=60,
    )
    vectors = await emb.embed(["a", "b", "a"], "doc")
    assert vectors[0] == pytest.approx([0.6, 0.8])  # единичная длина
    assert uris == ["emb://b1gfolder/text-search-doc/latest"] * 2  # дубль «a» не отправляется
    await emb.embed(["q"], "query")
    assert uris[-1] == "emb://b1gfolder/text-search-query/latest"
    await emb.embed(["a", "b"], "doc")
    assert len(uris) == 3  # из кэша
    await emb.aclose()


async def test_embeddings_failure_is_unavailable() -> None:
    emb = YandexEmbedder(
        client_with(httpx.MockTransport(lambda r: httpx.Response(401, text="no")), retries=0),
        doc_model="text-search-doc/latest",
        query_model="text-search-query/latest",
        concurrency=2,
        cooldown=60,
    )
    with pytest.raises(MlUnavailableError):
        await emb.embed(["a"], "doc")
    assert not emb.available
    await emb.aclose()


async def test_build_without_key_is_stub_and_with_key_is_yandex() -> None:
    no_key = Settings(
        llm_provider="yandex",
        embed_provider="yandex",
        yc_api_key="",
        yc_folder_id="",
        _env_file=None,
    )
    assert isinstance(build_llm(no_key), StubLLM)
    assert isinstance(build_embedder(no_key), StubEmbedder)

    with_key = Settings(
        llm_provider="yandex",
        embed_provider="yandex",
        yc_api_key="KEY",
        yc_folder_id="b1g",
        _env_file=None,
    )
    llm, emb = build_llm(with_key), build_embedder(with_key)
    assert isinstance(llm, YandexLLM) and isinstance(emb, YandexEmbedder)
    assert llm.model_uri == "gpt://b1g/yandexgpt-lite/latest"
    await llm.aclose()
    await emb.aclose()


async def test_similarity_thresholds_belong_to_each_provider() -> None:
    settings = Settings(
        embed_provider="ollama,yandex",
        yc_api_key="KEY",
        yc_folder_id="b1g",
        sim_low=0.4,
        sim_high=0.7,
        sim_low_yandex=0.5,
        sim_high_yandex=0.8,
        sim_retell_yandex=0.9,
        sim_same_news_yandex=0.88,
        _env_file=None,
    )
    chain = build_embedder(settings)
    assert isinstance(chain, FallbackEmbedder)
    ollama, ya = chain.providers
    assert (ollama.thresholds.low, ollama.thresholds.high) == (0.4, 0.7)
    assert ya.thresholds == SimilarityThresholds(0.5, 0.8, 0.9, 0.88)
    await chain.aclose()

    with pytest.raises(ValueError, match="пороги"):
        SimilarityThresholds(0.8, 0.5)

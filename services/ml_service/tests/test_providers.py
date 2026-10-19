"""Провайдеры Ollama на поддельном HTTP-транспорте + сборка по настройкам."""

import json

import httpx
import pytest

from ml_service.config import Settings
from ml_service.dependencies import build_engine
from ml_service.errors import MlUnavailableError
from ml_service.providers.embeddings import OllamaEmbedder, build_embedder
from ml_service.providers.llm import OllamaLLM, build_llm


def llm_with(handler: httpx.MockTransport) -> OllamaLLM:
    return OllamaLLM(
        "http://ollama",
        "qwen",
        timeout=1,
        keep_alive="1m",
        num_ctx=2048,
        cooldown=60,
        transport=handler,
    )


async def test_ollama_chat_sends_json_mode_and_returns_content() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"a": 1}'}})

    llm = llm_with(httpx.MockTransport(handle))
    assert await llm.complete_json("sys", "user") == '{"a": 1}'
    assert seen["format"] == "json" and seen["stream"] is False and seen["model"] == "qwen"
    await llm.aclose()


async def test_ollama_failure_opens_breaker() -> None:
    llm = llm_with(httpx.MockTransport(lambda r: httpx.Response(404, text="model not found")))
    assert llm.available
    with pytest.raises(MlUnavailableError, match="404"):
        await llm.complete_json("sys", "user")
    assert not llm.available  # следующие вызовы сразу идут в эвристику
    await llm.aclose()


async def test_ollama_embed_batches_normalizes_and_caches() -> None:
    requests: list[list[str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        requests.append(texts)
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0] for _ in texts]})

    emb = OllamaEmbedder(
        "http://ollama",
        "bge-m3",
        timeout=1,
        keep_alive="1m",
        batch_size=2,
        cooldown=60,
        transport=httpx.MockTransport(handle),
    )
    vectors = await emb.embed(["a", "b", "c", "a"], "doc")
    assert [len(r) for r in requests] == [2, 1]  # дубль «a» не отправляется, пачки по 2
    assert vectors[0] == pytest.approx([0.6, 0.8])  # единичная длина
    await emb.embed(["a", "c"], "doc")
    assert len(requests) == 2  # из кэша
    await emb.aclose()


async def test_ollama_embed_wrong_count_is_unavailable() -> None:
    emb = OllamaEmbedder(
        "http://ollama",
        "bge-m3",
        timeout=1,
        keep_alive="1m",
        batch_size=8,
        cooldown=60,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"embeddings": []})),
    )
    with pytest.raises(MlUnavailableError):
        await emb.embed(["a"], "query")
    assert not emb.available
    await emb.aclose()


async def test_unimplemented_or_unreachable_provider_does_not_crash_startup() -> None:
    yandex = Settings(llm_provider="yandex", embed_provider="yandex", _env_file=None)
    assert not build_llm(yandex).available and not build_embedder(yandex).available

    # Ollama не запущена: сервис собирается, а первый запрос уходит в эвристику с degraded
    ollama = Settings(
        llm_provider="ollama",
        embed_provider="ollama",
        ollama_url="http://127.0.0.1:9",
        _env_file=None,
    )
    engine = build_engine(ollama)
    analysis, degraded = await engine.analyze_query("ДТП в Красноярске")
    assert degraded and analysis.search_queries
    await engine.aclose()

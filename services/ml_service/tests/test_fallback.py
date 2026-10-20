"""ML-15: цепочка провайдеров «ollama,yandex» (ноут → Яндекс → эвристики), без сети."""

import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from ml_service.config import Settings
from ml_service.core.models import GroupInput, Post
from ml_service.core.query import analyze_query_heuristic
from ml_service.core.similarity import SimilarityThresholds
from ml_service.engine import MlEngine
from ml_service.errors import MlUnavailableError
from ml_service.providers.embeddings import OllamaEmbedder, StubEmbedder, build_embedder
from ml_service.providers.fallback import FallbackEmbedder, FallbackLLM
from ml_service.providers.liveness import ollama_timeout
from ml_service.providers.llm import OllamaLLM, StubLLM, build_judge_llm, build_llm
from ml_service.providers.yandex import YandexEmbedder, YandexLLM
from tests.fakes import FailingAfterEmbedder, FakeEmbedder, ScriptedLLM
from tests.test_models_path import ANALYSIS_JSON, QUERY

ANSWER = json.dumps(ANALYSIS_JSON, ensure_ascii=False)
POSTS = [
    Post(id="p1", text="В Красноярске ГИБДД провела рейд: проверяли пешеходные переходы у школ."),
    Post(id="p2", text="ДТП на Красноярском мосту: столкнулись два автомобиля, пострадавших нет."),
    Post(id="p3", text="В филармонии прошёл концерт органной музыки, зал был полон."),
]


# ───────────────────────── настройки ─────────────────────────


def test_provider_chain_is_parsed() -> None:
    s = Settings(llm_provider=" Ollama , YANDEX ", _env_file=None)
    assert s.llm_chain == ["ollama", "yandex"]
    assert s.embed_chain == ["ollama", "yandex"]  # EMBED_PROVIDER пустой — та же цепочка
    assert Settings(llm_provider="yandex", _env_file=None).llm_chain == ["yandex"]
    assert Settings(llm_provider="ollama,stub", _env_file=None).llm_chain == ["ollama"]
    assert Settings(llm_provider="stub", _env_file=None).llm_chain == []
    both = Settings(llm_provider="ollama,yandex", embed_provider="ollama", _env_file=None)
    assert both.embed_chain == ["ollama"]


def test_empty_embed_provider_from_env_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """compose передаёт EMBED_PROVIDER="" — раньше сервис падал на старте с ValidationError."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama,yandex")
    monkeypatch.setenv("EMBED_PROVIDER", "")
    assert Settings(_env_file=None).embed_chain == ["ollama", "yandex"]


@pytest.mark.parametrize("value", ["olama", "ollama,gpt", "stub,ollama"])
def test_unknown_provider_is_a_clear_startup_error(value: str) -> None:
    with pytest.raises(ValidationError, match="LLM_PROVIDER"):
        Settings(llm_provider=value, _env_file=None)


async def test_build_chain_by_settings() -> None:
    with_key = Settings(
        llm_provider="ollama,yandex",
        yc_api_key="KEY",
        yc_folder_id="b1g",
        ollama_judge_model="qwen2.5:3b-instruct",
        _env_file=None,
    )
    llm = build_llm(with_key)
    assert isinstance(llm, FallbackLLM)
    assert [type(p) for p in llm.providers] == [OllamaLLM, YandexLLM]
    judge = build_judge_llm(with_key, llm)
    assert isinstance(judge, FallbackLLM) and judge is not llm
    assert judge.providers[0].name == "ollama:qwen2.5:3b-instruct"
    assert judge.providers[1] is llm.providers[1]  # у Яндекса судья тот же — общий «автомат»
    emb = build_embedder(with_key)
    assert isinstance(emb, FallbackEmbedder)
    assert [type(p) for p in emb.providers] == [OllamaEmbedder, YandexEmbedder]
    for p in (llm, judge, emb):
        await p.aclose()

    # ключа Яндекса нет — цепочка ollama → stub: остаётся один Ollama, как раньше
    no_key = Settings(llm_provider="ollama,yandex", _env_file=None)
    assert isinstance(build_llm(no_key), OllamaLLM)
    assert isinstance(build_embedder(no_key), OllamaEmbedder)
    assert isinstance(build_llm(Settings(llm_provider="stub", _env_file=None)), StubLLM)
    assert isinstance(build_embedder(Settings(_env_file=None)), StubEmbedder)


# ───────────────────────── FallbackLLM ─────────────────────────


async def test_first_failed_answer_from_second_and_switch_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ollama = ScriptedLLM("ollama:qwen", fail=True)
    yandex = ScriptedLLM("yandex:gpt", ANSWER)
    llm = FallbackLLM([ollama, yandex])
    caplog.set_level(logging.INFO, logger="ml_service.providers.fallback")

    assert await llm.complete_json("s", "u") == ANSWER
    assert len(ollama.calls) == 1 and len(yandex.calls) == 1
    assert llm.active == "yandex:gpt"

    # ноут вернулся: снова ollama, в логе — переключение
    ollama.fail = False
    ollama.breaker_open = False
    ollama.script = lambda s, u: ANSWER
    await llm.complete_json("s", "u")
    assert llm.active == "ollama:qwen"
    assert "ml provider switched: llm yandex:gpt → ollama:qwen" in caplog.text
    assert llm.status()["providers"][0]["last_error"].endswith("connection refused")


async def test_breaker_open_first_is_skipped_without_request() -> None:
    ollama = ScriptedLLM("ollama:qwen", ANSWER)
    ollama.breaker_open = True  # недавно падал — автомат выключил
    yandex = ScriptedLLM("yandex:gpt", ANSWER)
    llm = FallbackLLM([ollama, yandex])
    assert llm.available
    await llm.complete_json("s", "u")
    assert ollama.calls == [] and len(yandex.calls) == 1


async def test_all_failed_is_unavailable_and_engine_answers_heuristically() -> None:
    llm = FallbackLLM([ScriptedLLM("ollama", fail=True), ScriptedLLM("yandex", fail=True)])
    with pytest.raises(MlUnavailableError, match="ollama.*yandex"):
        await llm.complete_json("s", "u")
    assert not llm.available and llm.active == "stub"

    llm = FallbackLLM([ScriptedLLM("ollama", fail=True), ScriptedLLM("yandex", fail=True)])
    analysis, degraded = await MlEngine(llm, StubEmbedder()).analyze_query(QUERY)
    assert degraded and analysis.search_queries


async def test_switch_to_yandex_is_not_degraded() -> None:
    """Пользователь не видит переключения: ответ Яндекса — тоже ответ модели."""
    llm = FallbackLLM([ScriptedLLM("ollama", fail=True), ScriptedLLM("yandex", ANSWER)])
    analysis, degraded = await MlEngine(llm, StubEmbedder()).analyze_query(QUERY)
    assert not degraded
    assert "ДТП Красноярск" in analysis.search_queries


# ───────────────────── FallbackEmbedder + движок ─────────────────────


def far_apart() -> SimilarityThresholds:
    return SimilarityThresholds(low=0.98, high=0.99, retell=0.999, same_news=0.999)


async def test_one_rpc_one_provider_when_ollama_dies_mid_call() -> None:
    """Ollama ответила вектором запроса и упала на постах → весь вызов заново у Яндекса:
    вектор запроса Ollama не смешивается с векторами постов Яндекса."""
    analysis = analyze_query_heuristic(QUERY)
    ollama = FailingAfterEmbedder(1, name="ollama:bge-m3")
    yandex = FakeEmbedder(name="yandex:text-search", salt="ya", thresholds=far_apart())
    engine = MlEngine(StubLLM(), FallbackEmbedder([ollama, yandex]))
    scores, _ = await engine.score_posts(QUERY, analysis, POSTS)

    assert ollama.kinds == ["query", "doc"]  # запрос посчитан, на постах упала
    assert yandex.kinds == ["query", "doc"]  # у Яндекса — и запрос, и посты заново

    # результат ровно как у одного Яндекса: и векторы, и пороги — его
    alone = MlEngine(
        StubLLM(), FakeEmbedder(name="yandex:text-search", salt="ya", thresholds=far_apart())
    )
    expected, _ = await alone.score_posts(QUERY, analysis, POSTS)
    assert engine.last_similarities == alone.last_similarities
    assert scores == expected


async def test_thresholds_come_from_the_provider_that_made_vectors() -> None:
    analysis = analyze_query_heuristic(QUERY)
    near = MlEngine(StubLLM(), FakeEmbedder(thresholds=SimilarityThresholds(0.0, 0.01)))
    far = MlEngine(StubLLM(), FakeEmbedder(thresholds=far_apart()))
    near_scores, _ = await near.score_posts(QUERY, analysis, POSTS)
    far_scores, _ = await far.score_posts(QUERY, analysis, POSTS)
    assert near.last_similarities == far.last_similarities  # векторы те же
    assert "по смыслу близко" in near_scores[0].explanation
    assert "по смыслу далеко" in far_scores[0].explanation
    assert near_scores[0].score > far_scores[0].score


async def test_all_embedders_down_score_and_group_without_vectors() -> None:
    chain = FallbackEmbedder(
        [FailingAfterEmbedder(0, name="ollama"), FailingAfterEmbedder(0, name="yandex")]
    )
    engine = MlEngine(StubLLM(), chain)
    scores, degraded = await engine.score_posts(QUERY, analyze_query_heuristic(QUERY), POSTS)
    assert degraded and len(scores) == len(POSTS) and engine.last_similarities is None
    assert chain.active == "stub"
    groups = await engine.group_posts([GroupInput(id=p.id, text=p.text) for p in POSTS])
    assert sorted(i for g in groups for i in g.post_ids) == ["p1", "p2", "p3"]


async def test_group_posts_uses_second_provider_whole() -> None:
    ollama = FailingAfterEmbedder(0, name="ollama")
    yandex = FakeEmbedder(name="yandex")
    engine = MlEngine(StubLLM(), FallbackEmbedder([ollama, yandex]))
    await engine.group_posts([GroupInput(id=p.id, text=p.text) for p in POSTS])
    assert yandex.kinds == ["doc"]
    assert engine.status()["embeddings"]["active"] == "yandex"


# ───────────────────── Ollama: быстро понять, что ноут пропал ─────────────────────


def ollama_with(handler: httpx.MockTransport, probe_after: float = 20.0) -> OllamaLLM:
    return OllamaLLM(
        "http://tunnel:11435",
        "qwen",
        timeout=40,
        keep_alive="1m",
        num_ctx=2048,
        cooldown=60,
        connect_timeout=2.5,
        probe_after=probe_after,
        transport=handler,
    )


def test_connect_timeout_is_short_and_read_timeout_is_long() -> None:
    t = ollama_timeout(40.0, 2.5)
    assert t.connect == 2.5 and t.read == 40.0
    assert ollama_timeout(40.0, 0).connect == 40.0


async def test_silent_tunnel_is_detected_by_probe_before_long_request() -> None:
    paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/version":
            raise httpx.ReadTimeout("туннель принял соединение и молчит", request=request)
        raise AssertionError("до /api/chat дойти не должны")

    llm = ollama_with(httpx.MockTransport(handle))
    with pytest.raises(MlUnavailableError):
        await llm.complete_json("s", "u")
    assert paths == ["/api/version"]
    assert not llm.available  # автомат выключил: следующие запросы — сразу к Яндексу
    await llm.aclose()


async def test_probe_only_after_silence() -> None:
    paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12"})
        return httpx.Response(200, json={"message": {"content": "{}"}})

    llm = ollama_with(httpx.MockTransport(handle))
    await llm.complete_json("s", "u")
    await llm.complete_json("s", "u")
    assert paths == ["/api/version", "/api/chat", "/api/chat"]  # второй раз — без проверки
    await llm.aclose()

    paths.clear()
    llm = ollama_with(httpx.MockTransport(handle), probe_after=0)
    await llm.complete_json("s", "u")
    assert paths == ["/api/chat"]
    await llm.aclose()


async def test_connection_refused_reason_is_human() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    llm = ollama_with(httpx.MockTransport(handle), probe_after=0)
    with pytest.raises(MlUnavailableError, match="нет соединения"):
        await llm.complete_json("s", "u")
    await llm.aclose()


# ───────────────────── HTTP /health ─────────────────────


async def test_http_health_shows_active_provider() -> None:
    import asyncio

    from ml_service.transport.http_health import start_health_server

    llm = FallbackLLM([ScriptedLLM("ollama", fail=True), ScriptedLLM("yandex", ANSWER)])
    engine = MlEngine(llm, FakeEmbedder(name="ollama:bge-m3"))
    await engine.analyze_query(QUERY)
    server = await start_health_server("127.0.0.1:0", engine.status)
    assert server is not None
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        raw = await reader.read()
        writer.close()
    finally:
        server.close()
    head, body = raw.split(b"\r\n\r\n", 1)
    assert head.startswith(b"HTTP/1.0 200")
    data = json.loads(body)
    assert data["status"] == "ok"
    assert data["llm"]["active"] == "yandex"
    assert data["llm"]["providers"][0] == {
        "name": "ollama",
        "available": False,
        "last_error": "ollama: connection refused",
    }
    assert data["embeddings"]["providers"][0]["name"] == "ollama:bge-m3"
    assert await start_health_server("", engine.status) is None

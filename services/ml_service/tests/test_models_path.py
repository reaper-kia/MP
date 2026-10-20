"""Путь «с моделью»: LLM-разбор, LLM-судья, эмбеддинги, бюджеты и фолбэки (на фейках)."""

import json
import time

from ml_service.core.models import Post, QueryType, Relevance, Sentiment
from ml_service.engine import EngineLimits, MlEngine
from ml_service.providers.embeddings import StubEmbedder
from ml_service.providers.llm import StubLLM
from tests.fakes import FakeEmbedder, FakeLLM, failing_llm, judge_script

QUERY = "Безопасность дорожного движения в Красноярском крае"
NEWS = (
    "В Красноярске 15 октября произошёл крупный пожар на складе бытовой техники. Пожарные "
    "ликвидировали возгорание за 3 часа. Пострадавших нет. Ущерб оценивается в 10 миллионов рублей."
)
ANALYSIS_JSON = {
    "query_type": "topic",
    "summary": "Тема: безопасность дорожного движения (ДТП, ГИБДД) в Красноярском крае",
    "search_queries": [
        "безопасность дорожного движения",
        "ДТП Красноярск",
        "ДТП Красноярск",
        "рейд ГИБДД",
        "Госавтоинспекция Красноярский край",
        "пешеходный переход",
        "",
    ],
    "entities": [{"text": "Красноярский край", "type": "location"}, {"text": "x", "type": "??"}],
    "must_concepts": ["дорожное движение"],
    "exclude_concepts": ["пожарная безопасность"],
    "needs_clarification": True,
    "clarification_hint": "Уточните",
}


def engine(llm=None, embedder=None, **limits) -> MlEngine:  # type: ignore[no-untyped-def]
    return MlEngine(
        llm=llm or StubLLM(),
        embedder=embedder or StubEmbedder(),
        limits=EngineLimits(**limits),
    )


# ───────────────────────── AnalyzeQuery ─────────────────────────


async def test_analyze_query_llm_is_used_and_cleaned() -> None:
    llm = FakeLLM(lambda s, u: json.dumps(ANALYSIS_JSON, ensure_ascii=False))
    analysis, degraded = await engine(llm).analyze_query(QUERY)
    assert not degraded
    assert analysis.query_type is QueryType.TOPIC
    assert analysis.search_queries[:2] == ["безопасность дорожного движения", "ДТП Красноярск"]
    assert len(analysis.search_queries) == len(set(map(str.lower, analysis.search_queries)))
    assert 3 <= len(analysis.search_queries) <= 8 and all(analysis.search_queries)
    assert "пожарная безопасность" in analysis.exclude_concepts
    # длинный конкретный запрос: «нужно уточнить» от модели не принимаем
    assert not analysis.needs_clarification and analysis.clarification_hint == ""
    assert all(e.text != "x" for e in analysis.entities)


async def test_news_text_type_is_decided_by_rule_not_llm() -> None:
    answer = {
        "query_type": "topic",
        "summary": "Пожар на складе",
        "search_queries": ["пожар склад"],
    }
    llm = FakeLLM(lambda s, u: json.dumps(answer, ensure_ascii=False))
    analysis, degraded = await engine(llm).analyze_query(NEWS)
    assert not degraded and analysis.query_type is QueryType.NEWS_TEXT
    # заголовок новости остаётся первой фразой поиска
    assert analysis.search_queries[0].startswith("В Красноярске 15 октября")


async def test_analyze_query_bad_json_twice_falls_back() -> None:
    llm = FakeLLM(lambda s, u: "Конечно! Вот ответ: {сломано")
    analysis, degraded = await engine(llm).analyze_query(QUERY)
    assert degraded and len(llm.calls) == 2  # одна повторная попытка
    assert analysis.search_queries


async def test_analyze_query_unavailable_and_slow_model() -> None:
    analysis, degraded = await engine(failing_llm()).analyze_query(QUERY)
    assert degraded and analysis.query_type is QueryType.TOPIC

    slow = FakeLLM(lambda s, u: json.dumps(ANALYSIS_JSON), delay=5)
    started = time.monotonic()
    _, degraded = await engine(slow, analyze_budget=0.2).analyze_query(QUERY)
    assert degraded and time.monotonic() - started < 2


async def test_clarification_for_one_generic_word() -> None:
    analysis, _ = await engine().analyze_query("безопасность")
    assert analysis.needs_clarification and "дорожная" in analysis.clarification_hint


async def test_clarification_for_news_without_topic() -> None:
    for query in ("новости", "новости Красноярска", "что нового в Красноярском крае"):
        analysis, _ = await engine().analyze_query(query)
        assert analysis.needs_clarification and analysis.clarification_hint, query
    analysis, _ = await engine().analyze_query("новости о ДТП в Ачинске")
    assert not analysis.needs_clarification


async def test_analyze_query_caches_successful_llm_call() -> None:
    calls = 0

    def fake_response(s: str, u: str) -> str:
        nonlocal calls
        calls += 1
        return json.dumps(ANALYSIS_JSON, ensure_ascii=False)

    eng = engine(FakeLLM(fake_response))
    res1, degraded1 = await eng.analyze_query("Тестовый запрос для кэша")
    assert not degraded1 and calls == 1

    # Повторный запрос должен мгновенно вернуться из кэша без вызова LLM
    res2, degraded2 = await eng.analyze_query("Тестовый запрос для кэша")
    assert not degraded2 and calls == 1
    assert res1.summary == res2.summary


async def test_clarification_hint_strips_other_regions() -> None:
    data = dict(ANALYSIS_JSON)
    data["needs_clarification"] = True
    data["clarification_hint"] = "Уточните тему в любом регионе или Красноярском крае"

    llm = FakeLLM(lambda s, u: json.dumps(data, ensure_ascii=False))
    analysis, _ = await engine(llm).analyze_query("безопасность")
    assert "в любом регионе" not in analysis.clarification_hint


# ───────────────────────── ScorePosts ─────────────────────────

POSTS = [
    Post(id="a", text="В Ачинске прошёл рейд ГИБДД: проверяли пешеходные переходы у школ."),
    Post(id="b", text="Пожарная безопасность в школах: прошли учения по эвакуации детей."),
    Post(id="c", text="Норильские школьники заняли призовые места на олимпиаде по физике."),
]


def decide(block: str) -> str:
    if "ГИБДД" in block:
        return "direct"
    if "Пожарная" in block:
        return "irrelevant"
    return "unrelated-garbage"  # не по схеме — пост должен остаться с оценкой v1


async def test_judge_sets_class_explanation_sentiment_and_caches() -> None:
    llm = FakeLLM(judge_script(decide, sentiment="positive"))
    eng = engine(llm, FakeEmbedder())
    # разбор «от LLM»: с синонимами («рейд ГИБДД») — как в жизни
    analyzer = FakeLLM(lambda s, u: json.dumps(ANALYSIS_JSON, ensure_ascii=False))
    analysis, _ = await engine(analyzer).analyze_query(QUERY)
    scores, degraded = await eng.score_posts(QUERY, analysis, POSTS)

    assert [s.id for s in scores] == ["a", "b", "c"]
    assert scores[0].relevance is Relevance.DIRECT
    assert scores[0].sentiment is Sentiment.POSITIVE
    assert scores[0].explanation.startswith("Пост о") and len(scores[0].explanation) <= 150
    assert scores[1].relevance is Relevance.IRRELEVANT
    assert scores[2].sentiment is None  # судья не дал оценку — тональность не выдумываем
    assert not degraded  # все посты видела хотя бы одна модель (эмбеддинги)
    for s, p in zip(scores, POSTS, strict=True):
        assert 0 <= s.excerpt_span.start < s.excerpt_span.end <= len(p.text)
        assert 0.0 <= s.score <= 1.0

    calls = len(llm.calls)
    await eng.score_posts(QUERY, analysis, POSTS[:2])
    assert len(llm.calls) == calls  # оба поста уже в кэше судьи


async def test_judge_budget_exceeded_returns_v1_in_time() -> None:
    llm = FakeLLM(judge_script(lambda b: "direct"), delay=5)
    analysis, _ = await engine().analyze_query(QUERY)
    started = time.monotonic()
    scores, degraded = await engine(llm, score_budget=0.3).score_posts(QUERY, analysis, POSTS)
    assert time.monotonic() - started < 2
    assert len(scores) == 3 and degraded  # ни судьи, ни эмбеддингов — чистая эвристика
    assert all(s.explanation.startswith("Упрощённая проверка") for s in scores)


async def test_unavailable_judge_and_embeddings_do_not_break_scoring() -> None:
    analysis, _ = await engine().analyze_query(QUERY)
    eng = engine(failing_llm(), FakeEmbedder(available=False))
    scores, degraded = await eng.score_posts(QUERY, analysis, POSTS)
    assert degraded and [s.id for s in scores] == ["a", "b", "c"]


async def test_strong_v1_vs_llm_irrelevant_becomes_disputed() -> None:
    analysis, _ = await engine().analyze_query(QUERY)
    post = Post(id="x", text="Рейд по безопасности дорожного движения прошёл в Канске.")
    llm = FakeLLM(judge_script(lambda b: "irrelevant"))
    scores, _ = await engine(llm).score_posts(QUERY, analysis, [post])
    assert scores[0].relevance is Relevance.DISPUTED


async def test_person_not_named_is_disputed_even_if_llm_says_direct() -> None:
    query = "Михаил Котюков губернатор Красноярского края"
    analysis, _ = await engine().analyze_query(query)
    assert analysis.query_type is QueryType.PERSON
    posts = [
        Post(id="1", text="Губернатор края посетил Норильск с рабочим визитом."),
        Post(id="2", text="Михаила Котюкова поздравили с победой команды «Енисей»."),
    ]
    llm = FakeLLM(judge_script(lambda b: "direct"))
    scores, _ = await engine(llm).score_posts(query, analysis, posts)
    assert scores[0].relevance is Relevance.DISPUTED and "Котюков" in scores[0].explanation
    assert scores[1].relevance is Relevance.DIRECT


async def test_news_conflict_beats_llm_same() -> None:
    analysis, _ = await engine().analyze_query(NEWS)
    other = Post(
        id="n",
        text="В Норильске 15 октября произошёл пожар на складе. Пожарные работали 2 часа.",
    )
    llm = FakeLLM(judge_script(lambda b: "same"))
    scores, _ = await engine(llm).score_posts(NEWS, analysis, [other])
    assert scores[0].relevance is Relevance.DISPUTED
    assert "Норильск" in scores[0].explanation

"""Инварианты контракта ml.v1 — должны выполняться при любой реализации (эвристика, модели)."""

import pytest

from ml_service.config import Settings
from ml_service.core.models import GroupInput, Post, QueryType, Relevance
from ml_service.core.region import find_region
from ml_service.dependencies import build_engine
from ml_service.engine import MlEngine
from ml_service.errors import InvalidRequestError

QUERY = "Безопасность дорожного движения в Красноярском крае"
NEWS = (
    "В Ачинске сотрудники Госавтоинспекции провели рейд у школ. Проверяли пешеходные переходы. "
    "Выявлено 12 нарушений. Водителей предупредили о штрафах. " * 3
)


@pytest.fixture
def engine() -> MlEngine:
    # явно stub и без .env: тесты не зависят от того, запущена ли у разработчика Ollama
    return build_engine(Settings(llm_provider="stub", embed_provider="stub", _env_file=None))


async def test_analyze_query(engine: MlEngine) -> None:
    analysis, degraded = await engine.analyze_query(QUERY)
    assert analysis.query_type is QueryType.TOPIC and analysis.search_queries and degraded
    news, _ = await engine.analyze_query(NEWS)
    assert news.query_type is QueryType.NEWS_TEXT
    with pytest.raises(InvalidRequestError):
        await engine.analyze_query("  ")


async def test_score_posts_invariants(engine: MlEngine) -> None:
    analysis, _ = await engine.analyze_query(QUERY)
    posts = [
        Post(id="a", text="В Ачинске прошёл рейд ГИБДД по безопасности дорожного движения."),
        Post(id="b", text="Норильские школьники заняли призовые места на олимпиаде."),
        Post(id="c", text="Короткий"),
    ]
    scores, _ = await engine.score_posts(QUERY, analysis, posts)
    assert [s.id for s in scores] == ["a", "b", "c"]
    for score, post in zip(scores, posts, strict=True):
        span = score.excerpt_span
        assert 0 <= span.start < span.end <= len(post.text) and span.end - span.start <= 300
        assert all(0 <= h.start < h.end <= len(post.text) for h in score.highlight_spans)
        assert 0.0 <= score.score <= 1.0 and score.explanation
    assert scores[0].relevance is Relevance.DIRECT
    assert scores[0].region_by_content and scores[0].region_evidence == "Ачинск"
    assert scores[1].relevance is Relevance.IRRELEVANT


async def test_score_posts_rejects_bad_input(engine: MlEngine) -> None:
    analysis, _ = await engine.analyze_query(QUERY)
    with pytest.raises(InvalidRequestError):
        await engine.score_posts(QUERY, analysis, [Post(id="x", text="a"), Post(id="x", text="b")])
    with pytest.raises(InvalidRequestError):
        await engine.score_posts(QUERY, analysis, [Post(id=str(i), text="t") for i in range(51)])


async def test_group_posts_every_post_once(engine: MlEngine) -> None:
    posts = [
        GroupInput(id="1", text=NEWS),
        GroupInput(id="2", text=NEWS + " Подробности позже."),
        GroupInput(id="3", text="Совсем другая новость про театр в Канске."),
    ]
    groups = await engine.group_posts(posts)
    ids = [pid for g in groups for pid in g.post_ids]
    assert sorted(ids) == ["1", "2", "3"]
    assert any(set(g.post_ids) == {"1", "2"} for g in groups)
    assert all(g.representative_post_id in g.post_ids for g in groups)


def test_region() -> None:
    assert find_region("Авария на трассе под Канском") == "Канск"
    assert find_region("Новости Новосибирска") == ""


async def test_region_only_query_is_not_rejected_wholesale(engine: MlEngine) -> None:
    analysis, _ = await engine.analyze_query("Красноярск")
    posts = [
        Post(id="1", text="В Красноярске открыли новую набережную."),
        Post(id="2", text="Курс доллара вырос на бирже."),
    ]
    scores, _ = await engine.score_posts("Красноярск", analysis, posts)
    assert scores[0].relevance is not Relevance.IRRELEVANT
    assert scores[1].relevance is Relevance.IRRELEVANT

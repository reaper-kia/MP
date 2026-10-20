"""ML-16: якорь темы — пост, где с запросом совпали только общие слова, не «прямая связь».

Случай с демо: «Соревнования по спортивному программированию» → фестиваль ГТО с пометкой «прямая».
"""

import pytest

from ml_service.core.anchor import build_anchors, is_specific, strong_words
from ml_service.core.models import Post, QueryAnalysis, QueryType, Relevance
from ml_service.core.query import _LlmAnalysis, analyze_query_heuristic, merge_analysis
from ml_service.core.scoring import build_context, score_post_v1
from ml_service.engine import EngineLimits, MlEngine
from ml_service.providers.embeddings import StubEmbedder
from ml_service.providers.llm import StubLLM
from tests.fakes import FakeLLM, judge_script

QUERY = "Соревнования по спортивному программированию"
GTO = Post(
    "gto",
    "Железногорцы вошли в число призеров фестиваля ГТО. Сборная Железногорска заняла пятое "
    "общекомандное место на краевом фестивале. В соревнованиях выступили 183 спортсмена.",
)
ROBO = Post(
    "robo",
    "Железногорские школьники — в числе призёров РОБОФИНИСТА-2026. В Кронштадте юные "
    "робототехники соревновались в самых разных дисциплинах.",
)
FESTIVAL = Post(
    "fest",
    "Программа фестиваля книжной культуры насыщенная: встречи с писателями и спортивная зона.",
)
ICPC = Post(
    "icpc",
    "В СФУ стартовал финал Первенства России по спортивному программированию: школьники "
    "решают олимпиадные задачи на C++ и Python.",
)
OLYMPIAD = Post("olymp", "Красноярские школьники стали призёрами олимпиады по программированию.")

# что вернула qwen2.5:7b на демо (диагностика 20.10): термин раздроблен, «соревнования» отдельно
BAD_MODEL = _LlmAnalysis(
    query_type="event",
    summary="Событие: соревнования по спортивному программированию",
    search_queries=[
        "соревнования по программированию",
        "программирование соревнования",
        "кодирование соревнования",
        "IT-соревнования",
        "кодирование турнир",
        "соревнования",
    ],
    must_concepts=["соревнования", "программирование"],
)
RAW_BAD = QueryAnalysis(
    query_type=QueryType.EVENT,
    summary=BAD_MODEL.summary,
    search_queries=BAD_MODEL.search_queries,
    must_concepts=BAD_MODEL.must_concepts,
)


def test_general_words_do_not_name_a_topic() -> None:
    assert not is_specific("соревнования")
    assert not is_specific("Новости Красноярского края")
    assert is_specific("хакатон")
    assert strong_words("Соревнования по спортивному программированию 20 октября") == [
        "спортивному",
        "программированию",
    ]
    # «программа» — общее слово, «программирование» — нет (по короткой основе обе «програ»)
    assert strong_words("программа программирование") == ["программирование"]


def test_anchor_tells_programming_from_sport_and_programme() -> None:
    anchors = build_anchors(QUERY, analyze_query_heuristic(QUERY))
    assert anchors.found_in(ICPC.text)
    assert anchors.found_in(OLYMPIAD.text)
    assert not anchors.found_in(GTO.text)
    assert not anchors.found_in(ROBO.text)
    assert not anchors.found_in(FESTIVAL.text)
    assert not anchors.found_in("Соревнования по спортивному ориентированию на Столбах.")


def test_model_split_term_is_repaired_in_merge() -> None:
    a = merge_analysis(BAD_MODEL, analyze_query_heuristic(QUERY), QUERY)
    assert a.must_concepts[0] == "спортивное программирование"
    assert "соревнования" not in a.must_concepts
    assert "соревнования" not in a.search_queries
    assert {"ГТО", "футбол"} <= set(a.exclude_concepts)
    assert "ICPC" in a.search_queries


def test_bad_model_analysis_alone_no_longer_makes_gto_direct() -> None:
    """Даже если разбор от модели плохой и таблицы нет: «соревнования» не даёт совпадения."""
    ctx = build_context(QUERY, RAW_BAD)
    gto = score_post_v1(GTO, ctx, similarity=None)
    icpc = score_post_v1(ICPC, ctx, similarity=None)
    assert gto.lexical == 0.0
    assert gto.score.relevance in {Relevance.DISPUTED, Relevance.IRRELEVANT}
    assert icpc.anchored and icpc.score.relevance is Relevance.DIRECT


def test_confident_embedding_anchors_a_paraphrase() -> None:
    ctx = build_context(QUERY, RAW_BAD)
    far = score_post_v1(GTO, ctx, similarity=0.2)
    near = score_post_v1(GTO, ctx, similarity=0.9)  # ≥ high (0.68): пересказ без слов запроса
    assert not far.anchored
    assert near.anchored


def _engine(decision: str, *, gate: bool = True) -> MlEngine:
    return MlEngine(
        StubLLM(),
        StubEmbedder(),
        judge_llm=FakeLLM(judge_script(lambda _block: decision)),
        limits=EngineLimits(anchor_gate=gate),
    )


async def test_judge_fooled_by_common_words_is_capped_to_disputed() -> None:
    """Скрин с демо: судья сказал «прямая» про ГТО → теперь максимум «спорная»."""
    analysis = merge_analysis(BAD_MODEL, analyze_query_heuristic(QUERY), QUERY)
    scores, _ = await _engine("direct").score_posts(QUERY, analysis, [GTO, ROBO, ICPC])
    by_id = {s.id: s for s in scores}
    assert by_id["gto"].relevance is Relevance.DISPUTED
    assert by_id["robo"].relevance is Relevance.DISPUTED
    assert "проверьте" in by_id["gto"].explanation
    assert by_id["icpc"].relevance is Relevance.DIRECT


async def test_judge_irrelevant_without_anchor_is_final() -> None:
    """Раньше: v1 «прямая» + судья «мимо» → «спорная» (мусор в «Спорных»). Без якоря — мимо."""
    analysis = merge_analysis(BAD_MODEL, analyze_query_heuristic(QUERY), QUERY)
    scores, _ = await _engine("irrelevant").score_posts(QUERY, analysis, [GTO, ICPC])
    by_id = {s.id: s for s in scores}
    assert by_id["gto"].relevance is Relevance.IRRELEVANT
    # с якорем правило полноты прежнее: v1 «прямая», судья «мимо» → решает человек
    assert by_id["icpc"].relevance is Relevance.DISPUTED


async def test_gate_off_is_the_old_behaviour() -> None:
    scores, _ = await _engine("direct", gate=False).score_posts(QUERY, RAW_BAD, [GTO])
    assert scores[0].relevance is Relevance.DIRECT


@pytest.mark.parametrize(
    "text",
    [
        "ГИБДД задержала нетрезвого водителя на Взлётке.",
        "ДТП на Октябрьском мосту: столкнулись два автомобиля.",
        "Водитель сбил пешехода на нерегулируемом переходе в Ачинске.",
    ],
)
def test_road_safety_posts_keep_their_anchor(text: str) -> None:
    """Демо-сценарий БДД: пост о ГИБДД / ДТП не обязан содержать тему целиком."""
    query = "Безопасность дорожного движения в Красноярском крае"
    assert build_anchors(query, analyze_query_heuristic(query)).found_in(text)


def test_news_text_has_no_anchor_gate() -> None:
    query = (
        "В Красноярске 15 октября произошёл пожар на складе. Пожарные ликвидировали возгорание. "
        "Пострадавших нет."
    )
    assert not build_anchors(query, analyze_query_heuristic(query)).active

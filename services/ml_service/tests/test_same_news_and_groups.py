"""Сценарий 2 (та же новость) и группы — на eval-наборе news_text.jsonl и синтетике."""

import json
from pathlib import Path

from ml_service.core.grouping import group_posts_heuristic
from ml_service.core.models import GroupInput, Post, Relevance
from ml_service.core.region import find_all_regions, find_region, places
from ml_service.core.same_news import score_news_posts
from ml_service.core.text import dates, quantities, stem
from ml_service.engine import MlEngine
from ml_service.providers.llm import StubLLM
from tests.fakes import FakeEmbedder

DATASET = Path(__file__).resolve().parents[3] / "eval" / "datasets" / "news_text.jsonl"


def rows() -> list[dict[str, str]]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]


def test_same_news_dataset_heuristic() -> None:
    data = rows()
    posts = [Post(id=r["post_id"], text=r["post_text"], title=r["title"]) for r in data]
    results = score_news_posts(data[0]["query"], posts)
    for r, res in zip(data, results, strict=True):
        assert res.score.relevance.value == r["label"], (r["note"], res.score.explanation)
    explanations = [res.score.explanation for res in results]
    assert explanations[1] == "Та же новость в сокращении"
    assert any("Норильск" in e and "2 вместо 3" in e for e in explanations)


def test_groups_dataset_copies_together_other_events_apart() -> None:
    data = rows()
    groups = group_posts_heuristic(
        [GroupInput(id=r["post_id"], text=r["post_text"], title=r["title"]) for r in data]
    )
    group_of = {pid: g.group_id for g in groups for pid in g.post_ids}
    assert sorted(group_of) == sorted(r["post_id"] for r in data)  # каждый ровно один раз
    same = {group_of[r["post_id"]] for r in data if r["label"] == "direct"}
    assert len(same) == 1
    assert all(group_of[r["post_id"]] not in same for r in data if r["label"] == "irrelevant")


async def test_many_copies_of_one_story_are_one_group() -> None:
    base = "В Канске открыли новый мост через реку Кан, движение запустят 20 ноября."
    posts = [GroupInput(id=f"c{i}", text=f"{base} Источник №{i}.") for i in range(40)]
    posts += [GroupInput(id=f"o{i}", text=f"Концерт хора в Ачинске, вечер {i}.") for i in range(3)]
    engine = MlEngine(llm=StubLLM(), embedder=FakeEmbedder())
    groups = await engine.group_posts(posts)
    biggest = max(groups, key=lambda g: len(g.post_ids))
    assert len(biggest.post_ids) == 40 and len(groups) <= 4


def test_text_helpers() -> None:
    assert stem("дорогу") == stem("дорогах") == "дорог"
    assert stem("Котюкова") == stem("Котюков")
    assert dates("15 октября и 14.10") == {(15, 10), (14, 10)}
    assert quantities("за 3 часа, ущерб 10 млн, школа №5")["час"] == {"3"}
    assert quantities("10 миллионов рублей")["мил"] == quantities("10 млн")["мил"]


def test_region_multiword_names() -> None:
    assert find_region("Футбольная команда Красноярска") == "Красноярск"
    assert find_region("экскурсия на Красноярской ГЭС") == "Красноярская ГЭС"
    assert find_all_regions("В Красноярском крае лесной пожар") == ["Красноярский край"]
    assert places("В Красноярском крае") == set()  # край совместим с любым городом края
    assert find_region("березовый лес") == ""


def test_relevance_enum_stable() -> None:
    assert [r.value for r in Relevance] == ["direct", "indirect", "disputed", "irrelevant"]

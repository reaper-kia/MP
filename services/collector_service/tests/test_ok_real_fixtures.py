"""Сверка разбора OK с НАСТОЯЩИМИ страницами из tests/fixtures/ok/real/<gid>/ (B1-12).

Файлы появляются после `python scripts/record_ok_fixtures.py`. Пока их нет, тесты пропускаются.
Проверяем то же, что человек в таблице сверки: ссылка ведёт на топик, текст из ленты = текст на
странице топика, дата в ленте = дата на странице (обе OK пишет по Москве, мы храним UTC).
"""

import gzip
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from collector_service.infra.ok.pages import parse_group, parse_topic_page, parse_topics_page
from tests.web_support import FIXTURES

REAL = FIXTURES / "ok" / "real"
TOPIC_URL = re.compile(r"^https://ok\.ru/group/\d+/topic/\d+$")
GROUPS = sorted(p for p in REAL.glob("*") if (p / "meta.json").is_file()) if REAL.is_dir() else []


def html(folder: Path, name: str) -> str:
    return gzip.decompress((folder / f"{name}.html.gz").read_bytes()).decode("utf-8")


def recorded_at(folder: Path) -> datetime:
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return datetime.fromisoformat(meta["recorded_at"])


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


pytestmark = pytest.mark.skipif(
    not GROUPS, reason="нет записанных страниц — запустите scripts/record_ok_fixtures.py"
)


@pytest.mark.parametrize("folder", GROUPS, ids=[p.name for p in GROUPS])
def test_real_group_and_feed_are_understood(folder: Path) -> None:
    now = recorded_at(folder)
    group = parse_group(html(folder, "group"))
    assert group is not None and group.gid == folder.name and group.name
    topics = parse_topics_page(html(folder, "topics"), now).topics
    assert topics, "лента топиков пуста или разметка OK изменилась"
    for topic in topics:
        assert TOPIC_URL.match(topic.url) and topic.text.strip()
        assert topic.published_at is not None, f"{topic.url}: дата не разобрана"
        assert topic.published_at <= now + timedelta(minutes=1), f"{topic.url}: дата из будущего"


@pytest.mark.parametrize("folder", GROUPS, ids=[p.name for p in GROUPS])
def test_real_topic_page_matches_feed(folder: Path) -> None:
    now = recorded_at(folder)
    feed = {t.tid: t for t in parse_topics_page(html(folder, "topics"), now).topics}
    pages = sorted(folder.glob("topic_*.html.gz"))
    assert pages, "страницы топиков не записаны"
    for path in pages:
        tid = path.name.removeprefix("topic_").removesuffix(".html.gz")
        topic = parse_topic_page(html(folder, f"topic_{tid}"), now)
        assert topic is not None and topic.tid == tid and topic.url.endswith(f"/topic/{tid}")
        in_feed = feed.get(tid)
        if in_feed is None:
            continue  # закреплённый / подгруженный позже — сверять не с чем
        assert norm(in_feed.text)[:100] in norm(topic.text), f"{topic.url}: текст другой"
        if in_feed.published_at and topic.published_at:
            shift = abs(in_feed.published_at - topic.published_at)
            assert shift <= timedelta(minutes=1), (
                f"{topic.url}: дата в ленте {in_feed.published_at:%d.%m %H:%M} UTC, "
                f"на странице {topic.published_at:%d.%m %H:%M} UTC"
            )

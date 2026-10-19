"""Сверка разбора с НАСТОЯЩИМИ ответами VK из tests/fixtures/vk/real/.

Файлы появляются после `python scripts/record_vk_fixtures.py` (нужен сервисный ключ). Пока их
нет, тесты пропускаются — разбор проверен только на синтетических fixtures, и это надо помнить.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from collector_service.infra.vk_api.mapping import (
    SourceCard,
    group_items,
    post_from_item,
    source_from_group,
)
from tests.vk_support import FIXTURES

REAL = FIXTURES / "real"
WALL_URL = re.compile(r"^https://vk\.com/wall-?\d+_\d+$")


def load(name: str) -> Any:
    path: Path = REAL / name
    if not path.exists():
        pytest.skip(f"нет записанного ответа {name} — запустите scripts/record_vk_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))["response"]


def test_real_group_is_understood() -> None:
    groups = group_items(load("groups_get_by_id.json"))
    assert groups, "groups.getById вернул не тот формат — поправьте group_items"
    source = source_from_group(groups[0])
    assert (
        source.external_id.startswith("-")
        and source.name
        and source.url.startswith("https://vk.com/")
    )


@pytest.mark.parametrize("name", ["wall_get.json", "newsfeed_search.json"])
def test_real_posts_are_understood(name: str) -> None:
    items = load(name)["items"]
    assert items, f"{name}: пустой ответ, сверять нечего"
    card = SourceCard(name="источник", url="https://vk.com/x")
    for item in items:
        post = post_from_item(item, card)
        assert post is not None, f"{name}: не разобрали пост {item.get('id')}"
        assert WALL_URL.match(post.url)
        assert post.published_at is not None and post.published_at.tzinfo is not None

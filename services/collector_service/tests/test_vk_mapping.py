"""Разбор ссылок и ответов VK. Чистые функции, без сети."""

from datetime import UTC, datetime

import pytest

from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.infra.vk_api.mapping import (
    SourceCard,
    card_from_group,
    card_from_user,
    fallback_card,
    group_items,
    group_ref_from_url,
    owner_id_from_external,
    post_from_item,
    source_from_group,
)
from tests.vk_support import fixture

CARD = SourceCard(name="Новости Красноярска", url="https://vk.com/krsk_news_test")


@pytest.mark.parametrize(
    ("url", "ref"),
    [
        ("vk.com/krsk_news", "krsk_news"),
        ("https://vk.com/krsk_news/", "krsk_news"),
        ("https://vk.com/club123", "123"),
        ("https://vk.com/public456", "456"),
        ("https://vk.com/event789", "789"),
        ("https://vk.ru/krsk_news", "krsk_news"),
        ("https://m.vk.com/krsk_news?from=groups", "krsk_news"),
        ("https://www.vk.com/krsk.news", "krsk.news"),
    ],
)
def test_group_ref_from_url(url: str, ref: str) -> None:
    assert group_ref_from_url(url) == ref


@pytest.mark.parametrize(
    "url",
    [
        "https://vk.com",  # нет имени
        "https://vk.com/id1",  # человек
        "https://vk.com/krsk/extra",  # лишний путь
        "https://vk.com/wall-1_2",  # пост, не сообщество
        "https://vk.com/%D0%B4%D0%B0",  # не латиница
    ],
)
def test_group_ref_rejects_non_communities(url: str) -> None:
    with pytest.raises(UnsupportedUrlError):
        group_ref_from_url(url)


def test_owner_id_from_external() -> None:
    assert owner_id_from_external("-12345678") == -12345678
    assert owner_id_from_external("555") == 555
    for bad in ("abc", "0", ""):
        with pytest.raises(UnsupportedUrlError):
            owner_id_from_external(bad)


def test_source_from_group_fixture() -> None:
    [group] = group_items(fixture("groups_get_by_id.json")["response"])
    source = source_from_group(group)
    assert (source.external_id, source.screen_name) == ("-100001", "krsk_news_test")
    assert source.url == "https://vk.com/krsk_news_test"
    assert (source.name, source.city, source.members_count) == (
        "Новости Красноярска",
        "Красноярск",
        184000,
    )
    assert source.platform is Platform.VK and not source.is_closed


def test_source_from_group_missing_optional_fields_stay_empty() -> None:
    source = source_from_group({"id": 5, "name": "Группа", "is_closed": 1})
    assert source.city is None and source.members_count is None and source.is_closed
    assert (source.screen_name, source.url) == ("club5", "https://vk.com/club5")


def test_group_items_understands_old_and_new_response_formats() -> None:
    item = {"id": 1}
    assert group_items({"groups": [item], "profiles": []}) == [item]
    assert group_items([item]) == [item]
    assert group_items({}) == [] and group_items(None) == []


def test_cards() -> None:
    assert card_from_group({"id": 7, "name": "Паблик", "screen_name": "pub"}) == (
        -7,
        SourceCard("Паблик", "https://vk.com/pub"),
    )
    assert card_from_user({"id": 555, "first_name": "Ольга", "last_name": "Тестова"}) == (
        555,
        SourceCard("Ольга Тестова", "https://vk.com/id555"),
    )
    assert fallback_card(-9) == SourceCard("club9", "https://vk.com/club9")
    assert fallback_card(9) == SourceCard("id9", "https://vk.com/id9")


def test_post_full_fields() -> None:
    item = {
        "id": 9008,
        "owner_id": -100001,
        "date": 1792353900,
        "text": "Текст поста",
        "views": {"count": 1200},
        "likes": {"count": 35},
        "reposts": {"count": 0},
        "comments": {"count": 7},
    }
    post = post_from_item(item, CARD)
    assert post is not None
    assert post.url == "https://vk.com/wall-100001_9008"
    assert (post.source_external_id, post.post_external_id) == ("-100001", "9008")
    assert post.published_at == datetime(2026, 10, 18, 20, 5, tzinfo=UTC)
    assert (post.metrics.views, post.metrics.likes, post.metrics.reposts) == (1200, 35, 0)
    assert post.metrics.comments == 7  # 0 — тоже настоящее значение, не «нет данных»
    assert (post.source_name, post.source_url) == (CARD.name, CARD.url)
    assert post.title is None and not post.is_repost and post.repost_of_url is None


def test_post_missing_metrics_and_date_stay_none() -> None:
    post = post_from_item({"id": 1, "owner_id": -5, "text": "Текст"}, CARD)
    assert post is not None
    assert post.published_at is None
    assert (post.metrics.views, post.metrics.likes, post.metrics.reposts) == (None, None, None)
    assert post.metrics.comments is None


def test_post_repost_joins_texts_and_links_original() -> None:
    item = {
        "id": 2,
        "owner_id": -5,
        "text": "Комментарий",
        "copy_history": [{"id": 77, "owner_id": -200002, "text": "Оригинал"}],
    }
    post = post_from_item(item, CARD)
    assert post is not None
    assert post.text == "Комментарий\n\nОригинал"
    assert post.is_repost and post.repost_of_url == "https://vk.com/wall-200002_77"


def test_repost_without_own_text_keeps_only_original() -> None:
    item = {
        "id": 2,
        "owner_id": -5,
        "text": "",
        "copy_history": [{"id": 77, "owner_id": -200002, "text": "Оригинал"}],
    }
    post = post_from_item(item, CARD)
    assert post is not None and post.text == "Оригинал"


def test_post_without_ids_is_dropped_and_empty_text_stays_empty() -> None:
    assert post_from_item({"owner_id": -5, "text": "x"}, CARD) is None
    assert post_from_item({"id": 1, "text": "x"}, CARD) is None
    empty = post_from_item({"id": 1, "owner_id": -5, "text": "  "}, CARD)
    assert empty is not None and empty.text == ""

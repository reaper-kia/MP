"""VkConnector на синтетических fixtures: resolve, collect, search, health. Без сети.

Fixtures в tests/fixtures/vk/ составлены вручную по документации VK (см. ключ "_synthetic"),
поэтому тесты проверяют нашу логику, а не соответствие настоящему API — его сверяют
записанные ответы из fixtures/vk/real/ (test_vk_real_fixtures.py), когда они есть.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from collector_service.applications.context import RequestContext
from collector_service.applications.limits import CollectLimits
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_mediator
from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
    UnsupportedUrlError,
)
from collector_service.domain.value_objects import Period
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry
from collector_service.infra.connectors.vk import VkConnector
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from tests.streams import gather
from tests.vk_support import ScriptedVk, fixture, network_down, ok, vk_error

PERIOD = Period(
    start=datetime(2026, 10, 5, tzinfo=UTC),
    end=datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC),
)
OWNER = "-100001"


async def no_sleep(seconds: float) -> None:
    return None


def connector(vk: ScriptedVk, token: str = "tok", clock: Any = None) -> VkConnector:
    client = VkApiClient(vk, token=token, version="5.199", limiter=RateLimiter(0), sleep=no_sleep)
    return VkConnector(client, **({"clock": clock} if clock else {}))


def wall_vk(**extra: Any) -> ScriptedVk:
    return ScriptedVk(
        groups_getById=fixture("groups_cards.json"),
        wall_get=fixture("wall_get_group.json"),
        **extra,
    )


# ---------- resolve ----------


async def test_resolve_returns_source_card() -> None:
    vk = ScriptedVk(groups_getById=fixture("groups_get_by_id.json"))
    source = await connector(vk).resolve("https://m.vk.com/club100001")
    assert source.external_id == "-100001" and source.name == "Новости Красноярска"
    [form] = vk.params("groups.getById")
    assert form["group_id"] == "100001"  # club100001 → числовой id
    assert form["fields"] == "city,members_count,is_closed"


async def test_resolve_by_short_name_and_old_response_format() -> None:
    group = fixture("groups_get_by_id.json")["response"]["groups"]
    vk = ScriptedVk(groups_getById=lambda _: {"response": group})  # старый формат — список
    source = await connector(vk).resolve("vk.com/krsk_news_test")
    assert source.screen_name == "krsk_news_test"
    assert vk.params("groups.getById")[0]["group_id"] == "krsk_news_test"


async def test_resolve_unknown_group_is_not_found() -> None:
    for reply in (vk_error(100), ok({"groups": [], "profiles": []})):
        with pytest.raises(SourceNotFoundError):
            await connector(ScriptedVk(groups_getById=reply)).resolve("vk.com/nobody_here")


async def test_resolve_garbage_is_unsupported_and_makes_no_request() -> None:
    vk = ScriptedVk()
    with pytest.raises(UnsupportedUrlError):
        await connector(vk).resolve("https://vk.com/id1")
    assert vk.calls == []


# ---------- collect ----------


async def test_collect_takes_period_posts_and_stops_at_first_old_post() -> None:
    vk = wall_vk()
    result = await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 300)

    # пропущены: закреплённый старый, «после периода», пост без текста; старее периода — стоп
    assert [p.post_external_id for p in result.posts] == ["9008", "9007", "9004"]
    assert not result.truncated
    assert result.warnings == ["Пропущено постов без текста: 1"]
    assert vk.methods().count("wall.get") == 1  # после остановки страницы не листаем


async def test_collect_post_fields() -> None:
    result = await gather(connector(wall_vk()).collect(OWNER, PERIOD, []), PERIOD, 300)
    plain, repost, bare = result.posts

    assert plain.url == "https://vk.com/wall-100001_9008"
    assert plain.source_external_id == OWNER
    assert (plain.source_name, plain.source_url) == (
        "Новости Красноярска",
        "https://vk.com/krsk_news_test",
    )
    assert plain.published_at == datetime(2026, 10, 18, 20, 5, tzinfo=UTC)
    assert (plain.metrics.views, plain.metrics.likes) == (1200, 35)
    assert (plain.metrics.reposts, plain.metrics.comments) == (4, 7)

    assert repost.is_repost and repost.repost_of_url == "https://vk.com/wall-200002_77"
    assert (
        repost.text == "Комментарий к репосту\n\nТекст оригинального поста о ДТП на трассе Р-255."
    )
    assert (repost.metrics.likes, repost.metrics.views) == (3, None)

    assert bare.metrics.views is None and bare.metrics.likes is None


async def test_collect_pinned_old_post_does_not_stop_the_walk() -> None:
    # закреплённый пост — первый в ответе и старый; посты после него всё равно собраны
    result = await gather(connector(wall_vk()).collect(OWNER, PERIOD, []), PERIOD, 300)
    assert "9001" not in [p.post_external_id for p in result.posts] and len(result.posts) == 3


async def test_collect_pages_until_old_posts_and_passes_offsets() -> None:
    def page(start_id: int, size: int, date: int) -> dict[str, Any]:
        return ok(
            {
                "count": 250,
                "items": [
                    {"id": start_id + i, "owner_id": -100001, "date": date, "text": f"пост {i}"}
                    for i in range(size)
                ],
            }
        )

    vk = ScriptedVk(
        groups_getById=fixture("groups_cards.json"),
        wall_get=[page(1, 100, 1792000000), page(101, 100, 1792000000), page(201, 50, 1792000000)],
    )
    result = await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 1000)
    assert len(result.posts) == 250 and not result.truncated
    assert [f["offset"] for f in vk.params("wall.get")] == ["0", "100", "200"]  # count=250 → стоп
    assert {f["count"] for f in vk.params("wall.get")} == {"100"}
    assert {f["owner_id"] for f in vk.params("wall.get")} == {OWNER}


async def test_collect_truncates_at_max_posts() -> None:
    result = await gather(connector(wall_vk()).collect(OWNER, PERIOD, []), PERIOD, 2)
    assert [p.post_external_id for p in result.posts] == ["9008", "9007"]
    assert result.truncated


async def test_collect_exactly_max_posts_is_not_truncated() -> None:
    result = await gather(connector(wall_vk()).collect(OWNER, PERIOD, []), PERIOD, 3)
    assert len(result.posts) == 3 and not result.truncated


async def test_collect_ignores_keywords_and_returns_everything_in_period() -> None:
    result = await gather(
        connector(wall_vk()).collect(OWNER, PERIOD, ["совсем не то"]), PERIOD, 300
    )
    assert len(result.posts) == 3


async def test_collect_gives_up_on_endless_wall_with_truncated_warning() -> None:
    endless = ok(
        {
            "count": 999999,
            "items": [{"id": 1, "owner_id": -100001, "date": 1792480000, "text": "после периода"}],
        }
    )
    vk = ScriptedVk(groups_getById=fixture("groups_cards.json"), wall_get=endless)
    result = await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 300)
    assert result.truncated and "предел глубины" in result.warnings[0]
    assert len(vk.params("wall.get")) == 50


async def test_collect_empty_wall() -> None:
    vk = ScriptedVk(
        groups_getById=fixture("groups_cards.json"), wall_get=ok({"count": 0, "items": []})
    )
    result = await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 300)
    assert result.posts == [] and result.warnings == [] and not result.truncated


async def test_collect_closed_group_is_private() -> None:
    vk = ScriptedVk(groups_getById=fixture("groups_cards.json"), wall_get=vk_error(15))
    with pytest.raises(SourcePrivateError):
        await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 300)


async def test_collect_unknown_group_is_not_found() -> None:
    vk = ScriptedVk(groups_getById=ok({"groups": []}), wall_get=ok({"count": 0, "items": []}))
    with pytest.raises(SourceNotFoundError):
        await gather(connector(vk).collect(OWNER, PERIOD, []), PERIOD, 300)
    assert "wall.get" not in vk.methods()


async def test_collect_user_wall_uses_users_get_for_the_name() -> None:
    wall = ok(
        {"count": 1, "items": [{"id": 31, "owner_id": 555, "date": 1792100000, "text": "Привет"}]}
    )
    vk = ScriptedVk(users_get=fixture("users_get.json"), wall_get=wall)
    result = await gather(connector(vk).collect("555", PERIOD, []), PERIOD, 300)
    [post] = result.posts
    assert post.source_name == "Ольга Тестова" and post.url == "https://vk.com/wall555_31"
    assert "groups.getById" not in vk.methods()


async def test_collect_rejects_garbage_source_id() -> None:
    with pytest.raises(UnsupportedUrlError):
        await gather(connector(ScriptedVk()).collect("not-a-number", PERIOD, []), PERIOD, 300)


# ---------- search ----------


def search_vk(**extra: Any) -> ScriptedVk:
    return ScriptedVk(
        newsfeed_search=[
            fixture("newsfeed_search_page1.json"),
            fixture("newsfeed_search_page2.json"),
        ],
        groups_getById=fixture("groups_cards.json"),
        users_get=fixture("users_get.json"),
        **extra,
    )


async def test_search_pages_with_cursor_dedupes_and_names_sources() -> None:
    vk = search_vk()
    result = await gather(
        connector(vk).search(["ДТП Красноярск"], PERIOD, ["Красноярск"]), PERIOD, 500
    )

    keys = [(p.source_external_id, p.post_external_id) for p in result.posts]
    assert keys == [("-100001", "9008"), ("-100002", "5001"), ("555", "31"), ("-100003", "7001")]
    assert not result.truncated
    assert result.warnings == ["Пропущено постов без текста: 1"]

    names = {p.source_external_id: p.source_name for p in result.posts}
    assert names == {
        "-100001": "Новости Красноярска",
        "-100002": "Норильск Сегодня",
        "555": "Ольга Тестова",  # автор-человек остаётся, имя — из users.get
        "-100003": "Канск Online",
    }
    user_post = next(p for p in result.posts if p.source_external_id == "555")
    assert user_post.url == "https://vk.com/wall555_31"


async def test_search_request_parameters() -> None:
    vk = search_vk()
    await gather(
        connector(vk).search(["ДТП Красноярск"], PERIOD, ["Красноярск", "Красноярский край"]),
        PERIOD,
        500,
    )
    first, second = vk.params("newsfeed.search")
    assert first["q"] == "ДТП Красноярск"
    assert (first["start_time"], first["end_time"]) == ("1791158400", "1792454399")
    assert first["count"] == "200" and "start_from" not in first
    assert second["start_from"] == "2/synthetic-cursor"
    # регион коннектор не применяет: фраза уходит в VK как есть
    assert all("Красноярский край" not in v for f in (first, second) for v in f.values())
    # названия источников — пачками, а не по одному
    assert len(vk.params("groups.getById")) == 1 and len(vk.params("users.get")) == 1


async def test_search_without_region_terms_works_the_same() -> None:
    result = await gather(connector(search_vk()).search(["ДТП"], PERIOD, []), PERIOD, 500)
    assert len(result.posts) == 4


async def test_search_merges_phrases_without_duplicates() -> None:
    page = fixture("newsfeed_search_page2.json")  # одна страница без курсора
    vk = ScriptedVk(
        newsfeed_search=page, groups_getById=fixture("groups_cards.json"), users_get=ok([])
    )
    result = await gather(
        connector(vk).search(["фраза один", "фраза два"], PERIOD, []), PERIOD, 500
    )
    assert [q["q"] for q in vk.params("newsfeed.search")] == ["фраза один", "фраза два"]
    assert [p.post_external_id for p in result.posts] == ["9008", "7001"]  # дубль схлопнут


async def test_search_truncates_at_max_posts() -> None:
    result = await gather(connector(search_vk()).search(["ДТП"], PERIOD, []), PERIOD, 2)
    assert len(result.posts) == 2 and result.truncated


async def test_search_one_failed_phrase_keeps_results_of_the_others() -> None:
    # ошибка 10 ретраится (4 попытки на «плохую» фразу), затем вторая фраза проходит
    vk = ScriptedVk(
        newsfeed_search=[*[vk_error(10)] * 4, fixture("newsfeed_search_page2.json")],
        groups_getById=fixture("groups_cards.json"),
        users_get=ok([]),
    )
    result = await gather(connector(vk).search(["плохая", "хорошая"], PERIOD, []), PERIOD, 500)
    assert len(result.posts) == 2
    assert any("Фраза «плохая» не обработана" in w for w in result.warnings)


async def test_search_all_phrases_failed_raises() -> None:
    vk = ScriptedVk(newsfeed_search=vk_error(6))
    with pytest.raises(RateLimitedError):
        await gather(connector(vk).search(["а", "б"], PERIOD, []), PERIOD, 500)


async def test_search_keeps_posts_when_source_names_cannot_be_fetched() -> None:
    vk = ScriptedVk(
        newsfeed_search=fixture("newsfeed_search_page2.json"),
        groups_getById=network_down(),
    )
    result = await gather(connector(vk).search(["ДТП"], PERIOD, []), PERIOD, 500)
    assert [p.source_name for p in result.posts] == [
        "club100001",
        "club100003",
    ]  # настоящие имена по id
    assert [p.source_url for p in result.posts] == [
        "https://vk.com/club100001",
        "https://vk.com/club100003",
    ]
    assert any("Названия источников" in w for w in result.warnings)


async def test_search_missing_source_card_is_counted_in_warnings() -> None:
    only_one = ok({"groups": [fixture("groups_cards.json")["response"]["groups"][0]]})
    vk = ScriptedVk(newsfeed_search=fixture("newsfeed_search_page2.json"), groups_getById=only_one)
    result = await gather(connector(vk).search(["ДТП"], PERIOD, []), PERIOD, 500)
    assert [p.source_name for p in result.posts] == ["Новости Красноярска", "club100003"]
    assert "Не удалось получить названия источников: 1" in result.warnings


async def test_search_nothing_found() -> None:
    vk = ScriptedVk(newsfeed_search=ok({"count": 0, "total_count": 0, "items": []}))
    result = await gather(connector(vk).search(["ничего"], PERIOD, []), PERIOD, 500)
    assert result.posts == [] and not result.truncated
    assert vk.methods() == ["newsfeed.search"]  # без постов названия не запрашиваем


# ---------- health ----------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_health_without_token_is_unavailable_and_makes_no_request() -> None:
    vk = ScriptedVk()
    info = await connector(vk, token="").health()
    assert info.health is Health.UNAVAILABLE and "Не настроен доступ" in info.note
    assert not info.source_mode_supported and not info.global_mode_supported
    assert info.platform is Platform.VK and info.title == "ВКонтакте"
    assert vk.calls == []


async def test_health_ok_is_cached_for_five_minutes() -> None:
    vk = ScriptedVk(users_get=ok([{"id": 1}]))
    clock = Clock()
    vk_connector = connector(vk, clock=clock)
    first = await vk_connector.health()
    assert first.health is Health.OK and first.note == "" and first.global_mode_supported
    clock.now += 299
    await vk_connector.health()
    assert len(vk.calls) == 1
    clock.now += 2
    await vk_connector.health()
    assert len(vk.calls) == 2


async def test_health_bad_token_is_unavailable_and_rechecked_after_a_minute() -> None:
    vk = ScriptedVk(users_get=[vk_error(5), ok([{"id": 1}])])
    clock = Clock()
    vk_connector = connector(vk, clock=clock)
    info = await vk_connector.health()
    assert info.health is Health.UNAVAILABLE and "ключ доступа недействителен" in info.note
    clock.now += 30
    assert (await vk_connector.health()).health is Health.UNAVAILABLE
    assert len(vk.calls) == 1
    clock.now += 31
    assert (await vk_connector.health()).health is Health.OK


async def test_health_rate_limited_is_degraded() -> None:
    info = await connector(ScriptedVk(users_get=vk_error(6))).health()
    assert info.health is Health.DEGRADED and info.source_mode_supported


async def test_health_network_down_is_unavailable() -> None:
    info = await connector(ScriptedVk(users_get=network_down())).health()
    assert info.health is Health.UNAVAILABLE and "не ответила" in info.note


# ---------- через Mediator: те же гарантии, что у остальных площадок ----------


async def test_through_mediator_resolve_detects_vk_and_search_is_finalized() -> None:
    vk = search_vk()
    vk.replies["groups.getById"] = [
        fixture("groups_get_by_id.json"),
        fixture("groups_cards.json"),
    ]
    registry = InMemoryConnectorRegistry([connector(vk)])
    mediator = build_mediator(registry, CollectLimits(per_source=300, per_search=500))
    ctx = RequestContext(request_id="t")

    source = await mediator.send(ResolveSourceQuery(ctx=ctx, url="m.vk.com/club100001"))
    assert source.external_id == "-100001"

    found = await mediator.send(
        SearchPlatformQuery(
            ctx=ctx, platform=Platform.VK, queries=["ДТП"], period=PERIOD, region_terms=[]
        )
    )
    assert len(found.posts) == 4
    assert all(p.platform is Platform.VK for p in found.posts)

    platforms = await mediator.send(GetPlatformsQuery(ctx=ctx))
    assert [p.platform for p in platforms] == [Platform.VK]


async def test_through_mediator_collect_and_unavailable_platform() -> None:
    registry = InMemoryConnectorRegistry([connector(wall_vk())])
    mediator = build_mediator(registry, CollectLimits(per_source=300, per_search=500))
    ctx = RequestContext(request_id="t")
    result = await mediator.send(
        CollectFromSourceQuery(
            ctx=ctx, platform=Platform.VK, source_external_id=OWNER, period=PERIOD
        )
    )
    assert len(result.posts) == 3

    no_token = InMemoryConnectorRegistry([connector(ScriptedVk(), token="")])
    mediator = build_mediator(no_token, CollectLimits(per_source=300, per_search=500))
    with pytest.raises(PlatformUnavailableError):
        await mediator.send(
            CollectFromSourceQuery(
                ctx=ctx, platform=Platform.VK, source_external_id=OWNER, period=PERIOD
            )
        )

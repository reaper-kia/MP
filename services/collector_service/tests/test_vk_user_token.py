"""Токен пользователя VK ID: автообновление, ошибка 5 → новый токен, ошибка 1051 → «везде»
через Яндекс site:vk.com + wall.getById. Без сети."""

import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import MethodUnavailableError, PlatformUnavailableError
from collector_service.domain.value_objects import Page, Period
from collector_service.infra.connectors.site_search import SiteSearch, WithSearchFallback
from collector_service.infra.connectors.vk import VkConnector
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.mapping import wall_ref_from_url
from collector_service.infra.vk_api.tokens import VKID_TOKEN_URL, VkIdToken
from collector_service.infra.yandex_search.client import SearchHit
from tests.vk_support import ScriptedVk, network_down, ok, vk_error

PERIOD = Period(
    start=datetime(2026, 10, 5, tzinfo=UTC),
    end=datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC),
)
NOW = 1_800_000_000.0


async def gather(pages: AsyncIterator[Page]) -> list[Page]:
    return [page async for page in pages]


async def no_sleep(seconds: float) -> None:
    return None


def state_file(tmp_path: Path, **state: Any) -> Path:
    path = tmp_path / "token.json"
    base = {"access_token": "old", "expires_at": NOW + 3600}
    base |= {"refresh_token": "r1", "device_id": "d"}
    path.write_text(json.dumps({**base, **state}))
    return path


def refreshed(access: str = "new", refresh: str = "r2") -> dict[str, Any]:
    return {"access_token": access, "refresh_token": refresh, "expires_in": 3600}


def tokens(vk: ScriptedVk, path: Path, now: float = NOW) -> VkIdToken:
    return VkIdToken(vk, path, "54832790", clock=lambda: now)


def client(vk: ScriptedVk, source: VkIdToken) -> VkApiClient:
    return VkApiClient(vk, tokens=source, version="5.199", limiter=RateLimiter(0), sleep=no_sleep)


# ───────────────────────── токен VK ID ─────────────────────────


async def test_fresh_token_is_used_without_refresh(tmp_path: Path) -> None:
    vk = ScriptedVk(users_get=ok([{"id": 1}]))
    await client(vk, tokens(vk, state_file(tmp_path))).call("users.get", user_ids=1)
    assert vk.methods() == ["users.get"] and vk.params("users.get")[0]["access_token"] == "old"


async def test_expiring_token_is_refreshed_and_rotation_is_saved(tmp_path: Path) -> None:
    path = state_file(tmp_path, expires_at=NOW + 30)  # меньше запаса в 2 минуты
    vk = ScriptedVk(auth=refreshed(), users_get=ok([{"id": 1}]))
    await client(vk, tokens(vk, path)).call("users.get", user_ids=1)

    assert vk.urls[0] == VKID_TOKEN_URL
    form = vk.params("auth")[0]
    assert form["grant_type"] == "refresh_token" and form["refresh_token"] == "r1"
    assert form["client_id"] == "54832790" and form["device_id"] == "d"
    assert vk.params("users.get")[0]["access_token"] == "new"
    saved = json.loads(path.read_text())
    assert saved["refresh_token"] == "r2" and saved["expires_at"] == NOW + 3600


async def test_error_5_refreshes_once_and_retries(tmp_path: Path) -> None:
    vk = ScriptedVk(auth=refreshed(), users_get=[vk_error(5), ok([{"id": 1}])])
    api = VkApiClient(
        vk,
        tokens=tokens(vk, state_file(tmp_path)),
        version="5.199",
        limiter=RateLimiter(0),
        max_attempts=1,  # повтор после обновления не тратит попытку
        sleep=no_sleep,
    )
    assert await api.call("users.get", user_ids=1) == [{"id": 1}]
    assert [f["access_token"] for f in vk.params("users.get")] == ["old", "new"]


async def test_error_5_after_refresh_is_reported(tmp_path: Path) -> None:
    vk = ScriptedVk(auth=refreshed(), users_get=vk_error(5))
    with pytest.raises(PlatformUnavailableError, match="ключ доступа недействителен") as info:
        await client(vk, tokens(vk, state_file(tmp_path))).call("users.get", user_ids=1)
    assert "ошибка 5" in info.value.detail
    assert len(vk.params("auth")) == 1


async def test_refresh_failure_tells_how_to_fix(tmp_path: Path) -> None:
    vk = ScriptedVk(auth=network_down())
    source = tokens(vk, state_file(tmp_path, expires_at=NOW - 1))
    with pytest.raises(PlatformUnavailableError) as info:
        await source.token()
    assert "vk_token.py" in info.value.detail  # как чинить — в лог, не сотруднику
    assert "vk_token.py" not in str(info.value)

    vk = ScriptedVk(auth={"error": "invalid_grant"})
    with pytest.raises(PlatformUnavailableError) as info:
        await tokens(vk, state_file(tmp_path, expires_at=NOW - 1)).token()
    assert "vk_token.py" in info.value.detail


async def test_new_login_on_disk_is_picked_up_without_restart(tmp_path: Path) -> None:
    path = state_file(tmp_path)
    vk = ScriptedVk(users_get=[vk_error(5), ok([{"id": 1}])])
    source = tokens(vk, path)
    # пока сборщик работал, человек заново вошёл через scripts/vk_token.py
    path.write_text(
        json.dumps(
            {"access_token": "relogin", "expires_at": NOW + 3600, "refresh_token": "r9"}
            | {"device_id": "d"}
        )
    )
    await client(vk, source).call("users.get", user_ids=1)
    assert [f["access_token"] for f in vk.params("users.get")] == ["old", "relogin"]
    assert vk.params("auth") == []  # обновлять не пришлось


async def test_missing_or_broken_file_is_not_configured(tmp_path: Path) -> None:
    vk = ScriptedVk()
    assert not tokens(vk, tmp_path / "nope.json").configured
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    assert not tokens(vk, broken).configured


# ───────────────────────── ссылки на посты ─────────────────────────


def test_garbled_city_from_user_token_is_dropped() -> None:
    from collector_service.infra.vk_api.mapping import source_from_group

    group = {"id": 1, "name": "МЧС", "screen_name": "mchs24", "is_closed": 0}
    garbled = source_from_group(group | {"city": {"id": 73, "title": "?4??4??4??4??5??4??6?"}})
    assert garbled.city is None
    assert source_from_group(group | {"city": {"title": "Красноярск"}}).city == "Красноярск"


def test_wall_ref_from_url() -> None:
    assert wall_ref_from_url("https://vk.com/wall-68039614_123660") == (-68039614, 123660)
    assert wall_ref_from_url("https://m.vk.ru/wall-1_2") == (-1, 2)
    assert wall_ref_from_url("https://vk.com/krsk?w=wall-1_2") == (-1, 2)
    assert wall_ref_from_url("https://vk.com/wall15_7") == (15, 7)
    assert wall_ref_from_url("https://vk.com/public68039614") is None
    assert wall_ref_from_url("https://vk.com/id1") is None
    assert wall_ref_from_url("https://evil.com/wall-1_2") is None
    assert wall_ref_from_url("https://vk.com/wall0_1") is None


ITEM = {"id": 5, "owner_id": -10, "from_id": -10, "date": 1_791_600_000, "text": "ДТП на Мира"}


async def test_read_post_uses_wall_get_by_id_with_group_name() -> None:
    vk = ScriptedVk(
        wall_getById=ok(
            {"items": [ITEM], "groups": [{"id": 10, "name": "Новости", "screen_name": "news"}]}
        )
    )
    connector = VkConnector(VkApiClient(vk, token="t", version="5.199", limiter=RateLimiter(0)))
    assert connector.accepts("https://vk.com/wall-10_5") and not connector.accepts(
        "https://vk.com/x"
    )
    post = await connector.read_post("https://vk.com/wall-10_5")
    assert post is not None and post.text == "ДТП на Мира" and post.source_name == "Новости"
    assert vk.params("wall.getById")[0]["posts"] == "-10_5"

    vk = ScriptedVk(wall_getById=ok({"items": []}))  # удалён / закрыт
    connector = VkConnector(VkApiClient(vk, token="t", version="5.199", limiter=RateLimiter(0)))
    assert await connector.read_post("https://vk.com/wall-10_5") is None


# ───────────────────────── «везде» при ошибке 1051 ─────────────────────────


class Yandex:
    def __init__(self, urls: Sequence[str], configured: bool = True) -> None:
        self.urls = list(urls)
        self.configured = configured
        self.texts: list[str] = []

    async def search(self, text: str, page: int = 0) -> list[SearchHit]:
        self.texts.append(text)
        return [SearchHit(url=u, title="", snippet="") for u in self.urls] if page == 0 else []


def fallback_vk(vk: ScriptedVk, yandex: Yandex, *, native: bool = True) -> WithSearchFallback:
    api = VkApiClient(vk, token="t", version="5.199", limiter=RateLimiter(0), sleep=no_sleep)
    connector = VkConnector(api)
    site = SiteSearch(yandex, "vk.com", connector)  # type: ignore[arg-type]
    return WithSearchFallback(connector, site, native=native)


async def test_1051_switches_to_yandex_and_opens_posts() -> None:
    vk = ScriptedVk(
        users_get=ok([{"id": 1}]),
        newsfeed_search=vk_error(1051),
        wall_getById=ok({"items": [ITEM], "groups": [{"id": 10, "name": "Новости"}]}),
    )
    yandex = Yandex(["https://vk.com/wall-10_5", "https://vk.com/public10"])
    wrapped = fallback_vk(vk, yandex)

    pages = await gather(wrapped.search(["ДТП", "пожар"], PERIOD, []))
    posts = [p for page in pages for p in page.posts]
    assert len(vk.params("newsfeed.search")) == 1  # остальные фразы не тратим
    assert yandex.texts == ["ДТП site:vk.com", "пожар site:vk.com"]
    assert posts and posts[0].platform is Platform.VK and posts[0].text == "ДТП на Мира"

    await gather(wrapped.search(["ДТП"], PERIOD, []))
    assert len(vk.params("newsfeed.search")) == 1  # второй раз сразу через Яндекс
    info = await wrapped.health()
    assert info.health is Health.OK and info.global_mode_supported and "Яндекс" in info.note


async def test_1051_without_yandex_key_is_clear_error() -> None:
    vk = ScriptedVk(newsfeed_search=vk_error(1051))
    with pytest.raises(PlatformUnavailableError, match="не настроен") as info:
        await gather(fallback_vk(vk, Yandex([], configured=False)).search(["ДТП"], PERIOD, []))
    assert "YC_SEARCH_API_KEY" in info.value.detail and "YC_" not in str(info.value)


async def test_native_search_is_kept_when_it_works() -> None:
    vk = ScriptedVk(newsfeed_search=ok({"items": [ITEM], "count": 1}), groups_getById=ok([]))
    yandex = Yandex([])
    pages = await gather(fallback_vk(vk, yandex).search(["ДТП"], PERIOD, []))
    assert sum(len(p.posts) for p in pages) == 1 and yandex.texts == []


async def test_native_search_off_is_not_tried_and_global_mode_is_off() -> None:
    """VK_NEWSFEED_SEARCH=false: newsfeed.search не зовём, «везде» во VK — источники каталога."""
    vk = ScriptedVk(users_get=ok([{"id": 1}]), newsfeed_search=vk_error(1051))
    wrapped = fallback_vk(vk, Yandex([], configured=False), native=False)
    info = await wrapped.health()
    assert info.health is Health.OK and info.source_mode_supported
    assert not info.global_mode_supported and "1051" in info.note
    with pytest.raises(PlatformUnavailableError, match="не настроен"):
        await gather(wrapped.search(["ДТП"], PERIOD, []))
    assert vk.params("newsfeed.search") == []

    yandex = Yandex(["https://vk.com/wall-10_5"])
    vk = ScriptedVk(
        newsfeed_search=vk_error(1051),
        wall_getById=ok({"items": [ITEM], "groups": [{"id": 10, "name": "Новости"}]}),
    )
    pages = await gather(fallback_vk(vk, yandex, native=False).search(["ДТП"], PERIOD, []))
    assert sum(len(p.posts) for p in pages) == 1 and yandex.texts == ["ДТП site:vk.com"]
    assert vk.params("newsfeed.search") == []


def test_1051_is_method_unavailable() -> None:
    assert issubclass(MethodUnavailableError, PlatformUnavailableError)

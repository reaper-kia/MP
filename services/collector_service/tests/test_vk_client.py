"""VkApiClient: токен, ретраи, лимитер, перевод ошибок VK. Без сети."""

import pytest

from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
)
from collector_service.infra.vk_api.client import VK_API_URL, VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.transport import FormPoster
from tests.vk_support import ScriptedVk, network_down, ok, vk_error

TOKEN = "secret-token-123"


class Sleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def make_client(
    vk: FormPoster, sleeper: Sleeper | None = None, token: str = TOKEN
) -> tuple[VkApiClient, Sleeper]:
    sleeper = sleeper or Sleeper()
    client = VkApiClient(
        vk,
        token=token,
        version="5.199",
        limiter=RateLimiter(0),
        sleep=sleeper,
    )
    return client, sleeper


async def test_token_and_version_go_in_form_not_in_url() -> None:
    vk = ScriptedVk(utils_getServerTime=ok(1))
    client, _ = make_client(vk)
    assert await client.call("utils.getServerTime", user_ids=1) == 1
    [(method, form)] = vk.calls
    assert method == "utils.getServerTime"
    assert form == {"user_ids": "1", "access_token": TOKEN, "v": "5.199"}
    assert vk.urls == [VK_API_URL + "utils.getServerTime"]
    assert TOKEN not in vk.urls[0]


async def test_no_token_means_unavailable_without_calling_vk() -> None:
    vk = ScriptedVk()
    client, _ = make_client(vk, token="")
    with pytest.raises(PlatformUnavailableError, match="доступ к площадке не настроен") as info:
        await client.call("wall.get", owner_id=-1)
    assert "VK_SERVICE_TOKEN" in info.value.detail and "VK_SERVICE_TOKEN" not in str(info.value)
    assert vk.calls == []


@pytest.mark.parametrize("code", [6, 10])
async def test_retries_on_6_and_10_with_growing_backoff(code: int) -> None:
    vk = ScriptedVk(users_get=[vk_error(code), vk_error(code), ok([{"id": 1}])])
    client, sleeper = make_client(vk)
    assert await client.call("users.get", user_ids=1) == [{"id": 1}]
    assert len(vk.calls) == 3
    assert sleeper.delays == [0.5, 1.0]


async def test_gives_up_after_max_attempts() -> None:
    vk = ScriptedVk(users_get=vk_error(10))
    client, sleeper = make_client(vk)
    with pytest.raises(PlatformUnavailableError):
        await client.call("users.get", user_ids=1)
    assert len(vk.calls) == 4
    assert sleeper.delays == [0.5, 1.0, 2.0]


async def test_error_6_after_retries_is_rate_limited() -> None:
    vk = ScriptedVk(users_get=vk_error(6))
    client, _ = make_client(vk)
    with pytest.raises(RateLimitedError):
        await client.call("users.get", user_ids=1)
    assert len(vk.calls) == 4


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (5, PlatformUnavailableError),
        (15, SourcePrivateError),
        (18, SourcePrivateError),
        (30, SourcePrivateError),
        (100, SourceNotFoundError),
        (113, SourceNotFoundError),
        (9, RateLimitedError),
        (29, RateLimitedError),
        (77, PlatformUnavailableError),
    ],
)
async def test_vk_error_codes_map_to_service_errors_without_retry(
    code: int, expected: type[Exception]
) -> None:
    vk = ScriptedVk(wall_get=vk_error(code))
    client, sleeper = make_client(vk)
    with pytest.raises(expected):
        await client.call("wall.get", owner_id=-1)
    assert len(vk.calls) == 1 and sleeper.delays == []


async def test_network_errors_are_retried_then_reported_without_secrets() -> None:
    vk = ScriptedVk(wall_get=network_down())
    client, _ = make_client(vk)
    with pytest.raises(PlatformUnavailableError) as info:
        await client.call("wall.get", owner_id=-1)
    assert len(vk.calls) == 4
    assert TOKEN not in str(info.value) and TOKEN not in info.value.detail
    assert "не ответила" in str(info.value) and "ConnectError" in info.value.detail


@pytest.mark.parametrize("payload", [[], {"something": 1}, "text"])
async def test_unexpected_payload_is_platform_unavailable(payload: object) -> None:
    vk = ScriptedVk(wall_get=lambda _: payload)
    client, _ = make_client(vk)
    with pytest.raises(PlatformUnavailableError, match="вернула ошибку") as info:
        await client.call("wall.get", owner_id=-1)
    assert "неожиданный ответ" in info.value.detail


async def test_limiter_spaces_requests_by_rate() -> None:
    now = [100.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(3.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(4):
        await limiter.wait()
    assert slept == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    now[0] += 10  # долго не звали — ждать не надо
    await limiter.wait()
    assert len(slept) == 3

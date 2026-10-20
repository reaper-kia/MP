"""GetPlatforms укладывается в таймаут gateway (5 с), даже если проверка площадки медленная."""

import asyncio
import time

from collector_service.applications.context import RequestContext
from collector_service.applications.handlers.platforms import GetPlatformsQueryHandler
from collector_service.applications.queries.platforms import GetPlatformsQuery
from collector_service.domain.enums import Health, Platform
from collector_service.domain.value_objects import PlatformInfo

QUERY = GetPlatformsQuery(ctx=RequestContext(request_id="test"))


class SlowConnector:
    platform = Platform.OK
    title = "Одноклассники"

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.finished = False

    async def health(self) -> PlatformInfo:
        await asyncio.sleep(self.delay)
        self.finished = True
        return PlatformInfo(Platform.OK, self.title, True, False, Health.OK, "ok")


class Registry:
    def __init__(self, *connectors: SlowConnector) -> None:
        self._connectors = connectors

    def all(self) -> tuple[SlowConnector, ...]:
        return self._connectors


async def test_slow_health_check_does_not_block_platforms() -> None:
    slow = SlowConnector(delay=0.5)
    handler = GetPlatformsQueryHandler(Registry(slow), wait_seconds=0.05)  # type: ignore[arg-type]
    started = time.monotonic()
    [info] = await handler.handle(QUERY)
    assert time.monotonic() - started < 0.4
    assert info.health is Health.DEGRADED and "Проверка" in info.note
    await asyncio.sleep(0.6)
    assert slow.finished  # проверка не отменилась, доработала в фоне


async def test_fast_health_check_is_returned_as_is() -> None:
    handler = GetPlatformsQueryHandler(Registry(SlowConnector(delay=0)))  # type: ignore[arg-type]
    [info] = await handler.handle(QUERY)
    assert info.health is Health.OK

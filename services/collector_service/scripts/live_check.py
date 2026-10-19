"""Живая проверка сборщика на настоящих площадках — тот же код, что в сервисе, без gRPC.

Запускать там, где есть сеть до площадок (не в CI):

    cd services/collector_service
    uv run python scripts/live_check.py                      # OK (группа НГС) + новостные сайты
    uv run python scripts/live_check.py --days 3 ok.ru/ngs24 newslab.ru vk.com/krsk_news
    VK_SERVICE_TOKEN=... uv run python scripts/live_check.py vk.com/krsk_news --search "ДТП"

Для каждой ссылки: resolve → сбор за N дней → сколько постов, даты, 5 ссылок для сверки руками
(открыть в браузере: текст и дата должны совпасть). Ключи берутся из .env, как у сервиса.
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from collector_service.applications.context import RequestContext
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_container
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import CollectorError
from collector_service.domain.value_objects import CollectResult, Period
from collector_service.infra.config import Settings

DEFAULT_SOURCES = ["ok.ru/ngs24", "ngs24.ru", "krsk.aif.ru"]


def show(title: str, result: CollectResult) -> None:
    dated = [p.published_at for p in result.posts if p.published_at]
    span = f"{min(dated):%d.%m %H:%M} … {max(dated):%d.%m %H:%M} UTC" if dated else "дат нет"
    print(f"  {title}: постов {len(result.posts)}, truncated={result.truncated}, {span}")
    for warning in result.warnings:
        print(f"    ! {warning}")
    for post in result.posts[:5]:
        when = f"{post.published_at:%d.%m %H:%M}" if post.published_at else "без даты"
        print(f"    {when}  {post.url}\n      {post.text[:110]!r}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="*", default=DEFAULT_SOURCES)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--search", action="append", default=[], help="фраза для режима «везде»")
    args = parser.parse_args()

    settings = Settings(collector_fake=False)
    container = build_container(settings)
    mediator = container.mediator
    ctx = RequestContext(request_id="live-check")
    now = datetime.now(UTC)
    period = Period(start=now - timedelta(days=args.days), end=now)
    try:
        print("Площадки:")
        for info in await mediator.send(GetPlatformsQuery(ctx=ctx)):
            print(
                f"  {info.title}: {info.health}, источники={info.source_mode_supported}, "
                f"везде={info.global_mode_supported}  {info.note}"
            )
        for url in args.sources:
            print(f"\n{url}")
            try:
                source = await mediator.send(ResolveSourceQuery(ctx=ctx, url=url))
                print(f"  {source.name} [{source.platform} {source.external_id}] {source.url}")
                result = await mediator.send(
                    CollectFromSourceQuery(
                        ctx=ctx,
                        platform=source.platform,
                        source_external_id=source.external_id,
                        period=period,
                    )
                )
                show(f"за {args.days} дн.", result)
            except CollectorError as exc:
                print(f"  ОШИБКА {type(exc).__name__}: {exc}")
        for phrase in args.search:
            for platform in (Platform.VK, Platform.OK, Platform.NEWS):
                try:
                    found = await mediator.send(
                        SearchPlatformQuery(
                            ctx=ctx, platform=platform, queries=[phrase], period=period
                        )
                    )
                    show(f"«{phrase}» везде на {platform}", found)
                except CollectorError as exc:
                    print(f"  «{phrase}» на {platform}: {type(exc).__name__}: {exc}")
    finally:
        await container.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())

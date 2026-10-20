"""Сверка достоверности (B1-12): посты VK и OK → таблица для docs/demo/.

Тот же код, что в сервисе (resolve → сбор за N дней через Mediator), плюс независимая перепроверка
каждого поста: OK — открываем страницу самого топика (лента и топик размечены по-разному),
VK — wall.getById по ссылке поста. Совпали текст и дата — ✔, нет — расхождение в таблицу.

Запускать там, где есть сеть до площадок (не в CI); ключи — из .env, как у сервиса:

    cd services/collector_service
    uv run python scripts/reliability_check.py                       # 3 группы OK из seed + VK
    uv run python scripts/reliability_check.py --days 7 --per-platform 5 \\
        --ok ok.ru/gornovosti --vk vk.com/news_ngs24 --out ../../docs/demo/reliability-check.md

Колонки «открылась у человека / текст / дата» скрипт оставляет пустыми (☐): их отмечает человек,
открыв ссылку в браузере без входа. Дата на страницах OK — по Москве, у нас хранится UTC,
интерфейс показывает Красноярск (МСК+4) — поэтому в таблице обе.
"""

import argparse
import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from collector_service.applications.context import RequestContext
from collector_service.applications.ports.connectors import PostReader
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_container, build_vk, build_web_fetcher
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import CollectorError, log_text
from collector_service.domain.value_objects import Period, RawPost, SourceInfo
from collector_service.infra.config import Settings
from collector_service.infra.connectors.ok import OkConnector

# три группы OK из seed/sources.xlsx и две крупные группы VK оттуда же
DEFAULT_OK = ["ok.ru/gornovosti", "ok.ru/delakrasnoyarsk", "ok.ru/group/57451052466232"]
DEFAULT_VK = ["vk.com/news_ngs24", "vk.com/gibdd24"]
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs" / "demo" / "reliability-check.md"

KRSK = ZoneInfo("Asia/Krasnoyarsk")
MSK = ZoneInfo("Europe/Moscow")
TITLES = {Platform.VK: "ВКонтакте", Platform.OK: "Одноклассники"}


@dataclass
class Row:
    post: RawPost
    recheck: str  # итог независимой перепроверки


@dataclass
class SourceReport:
    url: str
    source: SourceInfo | None = None
    posts: int = 0
    warnings: Sequence[str] = ()
    error: str = ""


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def same_text(ours: str, theirs: str) -> bool:
    """Лента может обрезать длинный текст — достаточно, чтобы начало одного было в другом."""
    a, b = norm(ours)[:200], norm(theirs)[:200]
    return bool(a and b) and (a in norm(theirs) or b in norm(ours))


def fmt(moment: datetime | None, tz: ZoneInfo) -> str:
    return f"{moment.astimezone(tz):%d.%m.%Y %H:%M}" if moment else "нет даты"


async def recheck(reader: PostReader, post: RawPost) -> str:
    try:
        again = await reader.read_post(post.url)
    except CollectorError as exc:
        return f"не открылась: {exc}"
    if again is None:
        return "не открылась: поста по ссылке нет"
    problems = []
    if not same_text(post.text, again.text):
        problems.append("текст другой")
    if post.published_at and again.published_at:
        shift = abs((post.published_at - again.published_at).total_seconds())
        if shift > 60:
            problems.append(
                f"дата: в ленте {fmt(post.published_at, MSK)}, "
                f"на странице {fmt(again.published_at, MSK)} МСК"
            )
    elif post.published_at != again.published_at:
        problems.append("дата есть только в одном месте")
    return "✔ текст и дата совпали" if not problems else "≠ " + "; ".join(problems)


def pick(posts: list[RawPost], count: int) -> list[RawPost]:
    """Самые свежие, но репост (если есть) — обязательно: его текст собирается из двух частей."""
    ordered = sorted(posts, key=lambda p: p.published_at or datetime.min.replace(tzinfo=UTC))
    ordered.reverse()
    chosen = ordered[:count]
    repost = next((p for p in ordered if p.is_repost), None)
    if repost is not None and repost not in chosen and chosen:
        chosen[-1] = repost
    return chosen


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(rows: list[Row], reports: list[SourceReport], days: int, started: datetime) -> str:
    out = [
        "# Сверка достоверности: VK и OK (B1-12)",
        "",
        f"Снято {started.astimezone(KRSK):%d.%m.%Y %H:%M} (Красноярск) скриптом "
        "`services/collector_service/scripts/reliability_check.py`, "
        f"сбор за {days} дн. тем же кодом, что в сервисе.",
        "",
        "«Перепроверка» — автоматически: пост открыт второй раз отдельно от ленты "
        "(OK — страница топика, VK — `wall.getById`), сравнены текст и дата. "
        "Три последние колонки отмечает человек: открыть ссылку в браузере **без входа**, "
        "сравнить текст и дату (на OK время московское, в интерфейсе — красноярское, МСК+4).",
        "",
        "| # | Площадка | Источник | Ссылка | Текст (начало) | Дата, Красноярск | Дата, МСК "
        "| Перепроверка | Открылась | Текст | Дата |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for number, row in enumerate(rows, 1):
        post = row.post
        kind = " (репост)" if post.is_repost else ""
        out.append(
            f"| {number} | {TITLES.get(post.platform, post.platform)}{kind} "
            f"| {cell(post.source_name)} | {post.url} | {cell(post.text[:80])}… "
            f"| {fmt(post.published_at, KRSK)} | {fmt(post.published_at, MSK)} "
            f"| {cell(row.recheck)} | ☐ | ☐ | ☐ |"
        )
    out += ["", "## Источники", ""]
    for report in reports:
        if report.error:
            out.append(f"- {report.url} — **ошибка:** {report.error}")
            continue
        assert report.source is not None
        city = f", {report.source.city}" if report.source.city else ""
        out.append(
            f"- {report.url} → «{report.source.name}»{city}, id `{report.source.external_id}`: "
            f"постов за период {report.posts}"
        )
        out += [f"  - ⚠ {w}" for w in report.warnings]
    mismatched = [r for r in rows if not r.recheck.startswith("✔")]
    out += ["", "## Расхождения и ограничения", ""]
    if not mismatched:
        out.append("- Автоматическая перепроверка расхождений не нашла.")
    out += [f"- {r.post.url}: {r.recheck}" for r in mismatched]
    out += [
        "- Пост VK без текста (только фото/видео) в подборку не попадает: правило ТЗ «нет "
        "текста — нет выдержки»; сколько таких пропущено — в предупреждениях источника выше.",
        "- Репост VK: показываем комментарий репостнувшего + текст оригинала, ссылка — на "
        "репост, ссылка на оригинал — отдельным полем.",
        "",
    ]
    return "\n".join(out)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ok", action="append", help="группа OK (можно несколько)")
    parser.add_argument("--vk", action="append", help="сообщество VK (можно несколько)")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-platform", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    settings = Settings(collector_fake=False)
    container = build_container(settings)
    readers: dict[Platform, PostReader] = {
        Platform.VK: build_vk(settings, container.http),
        Platform.OK: OkConnector(build_web_fetcher(settings, container.http)),
    }
    ctx = RequestContext(request_id="reliability-check")
    started = datetime.now(UTC)
    period = Period(start=started - timedelta(days=args.days), end=started)
    rows: list[Row] = []
    reports: list[SourceReport] = []
    try:
        plan = ((Platform.VK, args.vk or DEFAULT_VK), (Platform.OK, args.ok or DEFAULT_OK))
        for platform, urls in plan:
            collected: list[RawPost] = []
            for url in urls:
                report = SourceReport(url=url)
                reports.append(report)
                try:
                    report.source = await container.mediator.send(
                        ResolveSourceQuery(ctx=ctx, url=url)
                    )
                    result = await container.mediator.send(
                        CollectFromSourceQuery(
                            ctx=ctx,
                            platform=report.source.platform,
                            source_external_id=report.source.external_id,
                            period=period,
                        )
                    )
                except CollectorError as exc:
                    report.error = str(exc)
                    print(f"{url}: {log_text(exc)}")
                    continue
                report.posts, report.warnings = len(result.posts), result.warnings
                collected.extend(result.posts)
                print(f"{url}: «{report.source.name}», постов {len(result.posts)}")
            for post in pick(collected, args.per_platform):
                rows.append(Row(post=post, recheck=await recheck(readers[platform], post)))
                print(f"  {post.url}: {rows[-1].recheck}")
    finally:
        await container.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(rows, reports, args.days, started), encoding="utf-8")
    print(f"\nТаблица: {args.out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())

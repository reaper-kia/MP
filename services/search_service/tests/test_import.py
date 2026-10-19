"""Импорт источников из XLSX (B2-10): отчёт created / duplicates / failed с номером строки."""

import io

import pytest
from openpyxl import Workbook

from search_service.applications.commands.sources import ImportSourcesCommand
from search_service.applications.context import RequestContext
from search_service.applications.exceptions import SearchInvalidParamsError, UpstreamError
from search_service.applications.handlers.source_import import parse_sources_xlsx
from search_service.applications.handlers.sources import ImportSourcesCommandHandler
from search_service.applications.ports.collector_client import SourceInfo
from search_service.domain.errors import SearchInvalidParams
from tests.fakes import FakeCollector, InMemoryUoW


def xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def info(name: str, **extra: object) -> SourceInfo:
    base = dict(
        platform="vk", external_id=f"-{name}", screen_name=name, url=f"https://vk.com/{name}"
    )
    base.update(extra)
    return SourceInfo(name=f"Группа {name}", **base)  # type: ignore[arg-type]


@pytest.fixture
def collector() -> FakeCollector:
    fake = FakeCollector()
    for name in ("news", "gibdd", "mchs"):
        fake.sources[f"https://vk.com/{name}"] = info(name)
    fake.sources["https://vk.com/closed"] = info("closed", is_closed=True)
    return fake


async def run_import(collector: FakeCollector, content: bytes, uow: InMemoryUoW | None = None):
    uow = uow or InMemoryUoW()
    handler = ImportSourcesCommandHandler(uow, collector)
    return await handler.handle(
        ImportSourcesCommand(ctx=RequestContext(request_id="t"), xlsx=content)
    ), uow


def test_parse_skips_header_and_empty_rows_and_keeps_excel_numbers():
    rows, bad = parse_sources_xlsx(
        xlsx(
            [
                ["Ссылка", "Название", "Региональный"],
                ["https://vk.com/news", "Новости", "да"],
                [None, None, None],
                ["vk.com/gibdd", None, "нет"],
                ["vk.com/mchs", None, None],
            ]
        )
    )
    assert bad == []
    assert [(r.row, r.url, r.name, r.is_regional) for r in rows] == [
        (2, "https://vk.com/news", "Новости", True),
        (4, "vk.com/gibdd", None, False),
        (5, "vk.com/mchs", None, True),
    ]


def test_parse_without_header():
    rows, _ = parse_sources_xlsx(xlsx([["https://vk.com/news"]]))
    assert [r.row for r in rows] == [1]


def test_parse_reports_bad_rows():
    rows, bad = parse_sources_xlsx(
        xlsx([["https://vk.com/news", None, "возможно"], [None, "Без ссылки", None]])
    )
    assert rows == []
    assert [(b.row, b.value) for b in bad] == [(1, "https://vk.com/news"), (2, "Без ссылки")]
    assert "«да» или «нет»" in bad[0].message and "ссылка" in bad[1].message.lower()


def test_parse_rejects_non_xlsx():
    with pytest.raises(SearchInvalidParams, match="xlsx"):
        parse_sources_xlsx("это не excel".encode())


def test_parse_rejects_too_many_rows():
    with pytest.raises(SearchInvalidParams, match="не больше"):
        parse_sources_xlsx(xlsx([["https://vk.com/news"]] * 600))


async def test_import_creates_counts_duplicates_and_reports_failed_rows(collector):
    content = xlsx(
        [
            ["Ссылка", "Название", "Региональный"],
            ["https://vk.com/news", "Новости края", "да"],  # 2: создан
            ["https://vk.com/news", None, None],  # 3: дубль
            ["https://vk.com/nowhere", None, None],  # 4: нет такого источника
            ["https://vk.com/closed", None, None],  # 5: закрытая группа
            ["https://vk.com/gibdd", None, "нет"],  # 6: создан, не региональный
        ]
    )

    report, uow = await run_import(collector, content)

    assert (report.created, report.duplicates) == (2, 1)
    assert [(f.row, f.error.code) for f in report.failed] == [
        (4, "SOURCE_NOT_FOUND"),
        (5, "SOURCE_PRIVATE"),
    ]
    assert all(f.error.message for f in report.failed)
    sources = {s.screen_name: s for s in uow.sources.store.values()}
    assert sources["news"].name == "Новости края" and sources["news"].is_regional is True
    assert sources["gibdd"].name == "Группа gibdd" and sources["gibdd"].is_regional is False


async def test_import_passes_upstream_error_code_of_row(collector):
    async def not_ready(url: str) -> SourceInfo:
        raise UpstreamError("collector", "NOT_IMPLEMENTED", "OK пока не поддерживается")

    collector.resolve_source = not_ready  # type: ignore[method-assign]

    report, _ = await run_import(collector, xlsx([["https://ok.ru/group/1"]]))

    assert report.created == 0
    assert [(f.row, f.value, f.error.code) for f in report.failed] == [
        (1, "https://ok.ru/group/1", "NOT_IMPLEMENTED")
    ]


async def test_import_bad_file_is_invalid_params(collector):
    with pytest.raises(SearchInvalidParamsError):
        await run_import(collector, b"nope")

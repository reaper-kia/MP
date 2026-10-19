from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import datetime

from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.handlers.errors import domain_errors
from search_service.applications.handlers.results import (
    ResultFilter,
    ResultsHandler,
    filter_from_query,
)
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.results import ExportSearchQuery
from search_service.applications.results.read_models import ExportFile
from search_service.domain.entities import Source
from search_service.domain.enums import ExportFormat, Relevance
from search_service.domain.errors import NotFoundError

RELEVANCE_RU = {
    Relevance.DIRECT: "Прямая",
    Relevance.INDIRECT: "Косвенная",
    Relevance.DISPUTED: "Спорная",
    Relevance.IRRELEVANT: "Не связана",
}


class ExportHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.results = ResultsHandler(uow)

    async def to_xlsx(
        self, search_id: uuid.UUID, f: ResultFilter, sort: str = "relevance"
    ) -> tuple[bytes, str, str]:
        # тот же запрос, что и для экрана
        results, total, _, counts = await self.results.list_results(
            search_id,
            f,
            sort,
            limit=10000,
            offset=0,
            max_limit=10000,
        )

        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            pub_ids = [r.publication_id for r in results]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}
            # каталог источников
            source_keys = {(p.platform, p.source_external_id) for p in pubs}
            sources: dict[tuple[str, str], Source] = {}
            for pk in source_keys:
                s = await self.uow.sources.get_by_key(*pk)
                if s:
                    sources[pk] = s

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as e:
            raise RuntimeError("openpyxl не установлен") from e

        wb = Workbook()

        # ---- Лист «Подборка» ----
        ws = wb.active
        ws.title = "Подборка"
        header_font = Font(bold=True)
        header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

        # шапка файла
        header_lines = [
            ("Запрос", search.query),
            ("Как понят запрос", (search.query_analysis or {}).get("summary", "")),
            (
                "Период",
                f"{search.period.from_date.strftime('%d.%m.%Y')} — "
                f"{search.period.to_date.strftime('%d.%m.%Y')} (время Красноярска)",
            ),
            (
                "Режим",
                "по выбранным источникам"
                if search.mode == "selected"
                else "без ограничения списком",
            ),
            ("Площадки", ", ".join(search.platforms)),
            ("Сформировано", datetime.now().strftime("%d.%m.%Y %H:%M")),
            (
                "Публикаций в подборке",
                f"{counts['total']} (из них без даты: {counts['unknown_date']}; "
                f"исключено вручную: {counts['excluded']})",
            ),
        ]
        row = 1
        for label, value in header_lines:
            ws.cell(row=row, column=1, value=label).font = header_font
            ws.cell(row=row, column=2, value=value)
            row += 1
        row += 1

        # шапка таблицы
        columns = [
            "№",
            "Площадка",
            "Источник",
            "Ссылка на источник",
            "Заголовок / начало поста",
            "Дата публикации",
            "Ссылка на публикацию",
            "Выдержка",
            "Связь с запросом",
            "Почему",
            "Регион",
            "Тональность",
            "Сюжет №",
        ]
        for col_idx, name in enumerate(columns, 1):
            cell = ws.cell(row=row, column=col_idx, value=name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

        for idx, r in enumerate(results, 1):
            pub = pubs_by_id.get(r.publication_id)
            if not pub:
                continue
            source = sources.get((pub.platform, pub.source_external_id))
            source_name = source.name if source else pub.source_name
            source_url = source.url if source else pub.source_url

            # заголовок
            title = pub.title
            if not title:
                text = pub.text.strip()
                if len(text) <= 120:
                    title = text
                else:
                    cut = text[:120]
                    last_space = cut.rfind(" ")
                    if last_space > 60:
                        cut = cut[:last_space]
                    title = cut + "…"

            # выдержка
            if r.excerpt_start is not None and r.excerpt_end is not None:
                excerpt = pub.text[r.excerpt_start : r.excerpt_end]
            else:
                excerpt = pub.text[:300]

            date_str = (
                pub.published_at.strftime("%d.%m.%Y %H:%M") if pub.published_at else "недоступна"
            )
            relevance_ru = RELEVANCE_RU.get(r.relevance, "") if r.relevance else ""
            region = ""
            if r.region_by_source or r.region_by_content:
                region = "Красноярский край"
                if r.region_evidence:
                    region += f" ({r.region_evidence})"

            values = [
                idx,
                pub.platform.upper(),
                source_name,
                source_url,
                title,
                date_str,
                pub.url,
                excerpt,
                relevance_ru,
                r.explanation,
                region,
                r.sentiment or "",
                r.group_id or "",
            ]
            for col_idx, value in enumerate(values, 1):
                cell = ws.cell(row=row, column=col_idx, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if col_idx == 7 and value:
                    cell.hyperlink = value
                    cell.font = Font(color="0563C1", underline="single")
            row += 1

        # ширины
        widths = [5, 8, 20, 30, 40, 16, 40, 50, 14, 40, 20, 12, 16]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        # автофильтр и заморозка
        header_row = 1 + len(header_lines) + 1
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{row - 1}"
        ws.freeze_panes = f"A{header_row + 1}"

        # ---- Лист «Охват» ----
        ws2 = wb.create_sheet("Охват")
        cov_cols = ["Площадка", "Источник", "Статус", "Получено", "В подборке", "Ошибка"]
        for i, name in enumerate(cov_cols, 1):
            cell = ws2.cell(row=1, column=i, value=name)
            cell.font = header_font
            cell.fill = header_fill
        r2 = 2
        for t in search.targets:
            ws2.cell(row=r2, column=1, value=t.platform.upper())
            ws2.cell(row=r2, column=2, value=t.name)
            ws2.cell(row=r2, column=3, value=t.status.value)
            ws2.cell(row=r2, column=4, value=t.fetched)
            ws2.cell(row=r2, column=5, value=t.matched)
            ws2.cell(row=r2, column=6, value=t.error_message or "")
            r2 += 1
        for i, w in enumerate([10, 30, 12, 10, 12, 50], 1):
            ws2.column_dimensions[get_column_letter(i)].width = w

        buf = io.BytesIO()
        wb.save(buf)
        filename = f"podborka_{search.period.to_date.isoformat()}_{str(search.id)[:8]}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return buf.getvalue(), filename, mime


# ---------------------------------------------------------------------------
# Хэндлер медиатора для gRPC-транспорта (регистрируется в dependencies.build_mediator).
# ---------------------------------------------------------------------------


@dataclass
class ExportSearchQueryHandler:
    uow: UnitOfWork

    async def handle(self, query: ExportSearchQuery) -> ExportFile:
        """Строки — тем же запросом, что ListResults (без limit), тот же filter и sort →
        файл совпадает с экраном. Формат листов — B2-08."""
        if query.format is not ExportFormat.XLSX:
            raise NotImplementedYetError("ExportSearch DOCX: B2-08")
        with domain_errors():
            content, filename, mime = await ExportHandler(self.uow).to_xlsx(
                query.search_id, filter_from_query(query.filter), sort=query.sort.value
            )
        return ExportFile(content=content, filename=filename, mime_type=mime)

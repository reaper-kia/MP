"""Выгрузка. XLSX — B2-08 (обязательно), DOCX — B2-10."""

from dataclasses import dataclass

from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.queries.results import ExportSearchQuery
from search_service.applications.results.read_models import ExportFile

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class ExportSearchQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ExportSearchQuery) -> ExportFile:
        """Строки — тем же запросом, что ListResults (без limit), тот же filter и sort →
        файл совпадает с экраном. Формат листов — B2-08."""
        raise NotImplementedYetError("ExportSearch: B2-08")

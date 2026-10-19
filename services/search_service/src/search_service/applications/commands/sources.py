from dataclasses import dataclass
from uuid import UUID

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import ImportReport, SourceView


@dataclass(frozen=True)
class CreateSourceCommand(Command[SourceView]):
    ctx: RequestContext
    url: str
    name: str | None = None  # None — взять с площадки
    is_regional: bool = True
    notes: str = ""


@dataclass(frozen=True)
class UpdateSourceCommand(Command[SourceView]):
    """None — поле не менять."""

    ctx: RequestContext
    source_id: UUID
    name: str | None = None
    is_regional: bool | None = None
    is_active: bool | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DeleteSourceCommand(Command[None]):
    ctx: RequestContext
    source_id: UUID


@dataclass(frozen=True)
class ImportSourcesCommand(Command[ImportReport]):
    ctx: RequestContext
    xlsx: bytes

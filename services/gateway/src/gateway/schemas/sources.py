from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from gateway.schemas.common import opt, ts
from gateway.schemas.enums import PLATFORM_FROM_PROTO, Platform


class SourceOut(BaseModel):
    id: UUID
    platform: Platform
    external_id: str
    url: str
    name: str
    city: str | None
    is_regional: bool
    is_active: bool
    notes: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_proto(cls, s: Any) -> "SourceOut":
        return cls(
            id=UUID(s.id),
            platform=PLATFORM_FROM_PROTO[s.platform],
            external_id=s.external_id,
            url=s.url,
            name=s.name,
            city=opt(s, "city"),
            is_regional=s.is_regional,
            is_active=s.is_active,
            notes=s.notes,
            created_at=ts(s.created_at),
            updated_at=ts(s.updated_at),
        )


class SourcePageOut(BaseModel):
    items: list[SourceOut]
    total: int
    has_more: bool


class SourceCreateIn(BaseModel):
    url: str = Field(min_length=3, examples=["https://vk.com/krsk_news"])
    name: str | None = Field(default=None, description="Пусто — взять с площадки")
    is_regional: bool = True
    notes: str = ""


class SourceUpdateIn(BaseModel):
    """Все поля необязательные: не передал — не меняется."""

    name: str | None = None
    is_regional: bool | None = None
    is_active: bool | None = None
    notes: str | None = None


class SourceResolveIn(BaseModel):
    url: str = Field(min_length=3, examples=["vk.com/krsk_news"])


class SourcePreviewOut(BaseModel):
    platform: Platform
    external_id: str
    url: str
    name: str
    city: str | None
    members_count: int | None
    existing_source_id: str | None

    @classmethod
    def from_proto(cls, p: Any) -> "SourcePreviewOut":
        return cls(
            platform=PLATFORM_FROM_PROTO[p.platform],
            external_id=p.external_id,
            url=p.url,
            name=p.name,
            city=opt(p, "city"),
            members_count=opt(p, "members_count"),
            existing_source_id=opt(p, "existing_source_id"),
        )


class ImportFailedRowOut(BaseModel):
    row: int
    value: str
    code: str
    message: str


class SourceImportReportOut(BaseModel):
    created: int
    duplicates: int
    failed: list[ImportFailedRowOut]

    @classmethod
    def from_proto(cls, r: Any) -> "SourceImportReportOut":
        return cls(
            created=r.created,
            duplicates=r.duplicates,
            failed=[
                ImportFailedRowOut(
                    row=f.row, value=f.value, code=f.error.code, message=f.error.message
                )
                for f in r.failed
            ],
        )

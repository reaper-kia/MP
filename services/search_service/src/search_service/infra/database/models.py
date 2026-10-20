from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, REAL, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# общий Base: migrations/env.py берёт таблицы из search_service.infra.database.base.Base.metadata
from search_service.infra.database.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SourceModel(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(Text)
    screen_name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_regional: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        Index(
            "ix_sources_platform_external",
            "platform",
            "external_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class SearchModel(Base):
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(Text)
    query_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(16))
    platforms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    source_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    query_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    stage: Mapped[str] = mapped_column(String(24))
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # подборка из кэша (B2-20): с какого поиска снята копия и когда тот завершился
    cached_from_search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # анонимный id браузера (X-Client-Id): история поисков у каждого своя
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    targets: Mapped[list[SearchTargetModel]] = relationship(
        "SearchTargetModel", back_populates="search", cascade="all, delete-orphan"
    )


class SearchTargetModel(Base):
    __tablename__ = "search_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("searches.id"))
    kind: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    search: Mapped[SearchModel] = relationship("SearchModel", back_populates="targets")


class PublicationModel(Base):
    __tablename__ = "publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(16))
    source_external_id: Mapped[str] = mapped_column(Text)
    post_external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    is_repost: Mapped[bool] = mapped_column(Boolean, default=False)
    repost_of_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "platform", "source_external_id", "post_external_id", name="uq_publications_post_key"
        ),
    )


class SearchResultModel(Base):
    __tablename__ = "search_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("searches.id"))
    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id")
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("search_targets.id")
    )
    relevance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    region_by_source: Mapped[bool] = mapped_column(Boolean, default=False)
    region_by_content: Mapped[bool] = mapped_column(Boolean, default=False)
    region_evidence: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    excerpt_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highlights: Mapped[list[list[int]]] = mapped_column(JSON, default=list)
    group_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_status: Mapped[str] = mapped_column(String(16))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("search_id", "publication_id", name="uq_search_publication"),
        Index("ix_results_search_relevance_excluded", "search_id", "relevance", "excluded"),
    )

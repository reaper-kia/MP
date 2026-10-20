from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from search_service.domain.enums import (
    TERMINAL_SEARCHES,
    TERMINAL_TARGETS,
    DateStatus,
    Relevance,
    SearchMode,
    SearchStage,
    SearchStatus,
    TargetStatus,
)
from search_service.domain.errors import DomainError
from search_service.domain.value_objects import Period


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Source:
    platform: str
    external_id: str
    screen_name: str
    url: str
    name: str
    city: str | None = None
    is_regional: bool = True
    is_active: bool = True
    notes: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def soft_delete(self) -> None:
        self.deleted_at = utcnow()
        self.updated_at = self.deleted_at

    def update(self, **fields: object) -> None:
        for k, v in fields.items():
            if v is not None:
                setattr(self, k, v)
        self.updated_at = utcnow()

    @property
    def is_alive(self) -> bool:
        return self.deleted_at is None


@dataclass
class SearchTarget:
    kind: str
    platform: str
    name: str
    url: str | None = None
    source_id: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    search_id: uuid.UUID | None = None
    status: TargetStatus = TargetStatus.PENDING
    fetched: int = 0
    matched: int = 0
    attempts: int = 0
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def start(self) -> None:
        self.status = TargetStatus.RUNNING
        self.attempts += 1
        self.started_at = utcnow()

    def mark_done(self, fetched: int, matched: int = 0) -> None:
        self.fetched, self.matched = fetched, matched
        self._finish(TargetStatus.DONE)

    def mark_empty(self) -> None:
        self._finish(TargetStatus.EMPTY)

    def mark_failed(self, code: str, message: str) -> None:
        self.error_code, self.error_message = code, message
        self._finish(TargetStatus.FAILED)

    def mark_skipped(self) -> None:
        self._finish(TargetStatus.SKIPPED)

    def _finish(self, status: TargetStatus) -> None:
        if self.status in TERMINAL_TARGETS:
            raise DomainError(f"target {self.id} уже в терминальном статусе {self.status}")
        self.status = status
        self.finished_at = utcnow()

    @property
    def is_finished(self) -> bool:
        return self.status in TERMINAL_TARGETS


@dataclass
class Search:
    query: str
    period: Period
    mode: SearchMode
    platforms: list[str] = field(default_factory=list)
    source_ids: list[uuid.UUID] = field(default_factory=list)
    targets: list[SearchTarget] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    query_type: str | None = None
    query_analysis: dict[str, Any] | None = None
    status: SearchStatus = SearchStatus.QUEUED
    stage: SearchStage = SearchStage.ANALYZING_QUERY
    warnings: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # подборка из кэша (B2-20): копия поиска cached_from_search_id, завершённого в cached_at
    cached_from_search_id: uuid.UUID | None = None
    cached_at: datetime | None = None
    # анонимный id браузера, запустившего поиск: история у каждого своя (не авторизация)
    owner: str = ""

    def start(self) -> None:
        if self.status is not SearchStatus.QUEUED:
            raise DomainError(f"start из статуса {self.status}")
        self.status = SearchStatus.RUNNING
        self.started_at = utcnow()
        self.finished_at = None  # повторный запуск (RetrySearch)

    def cancel(self) -> None:
        if self.status in TERMINAL_SEARCHES:
            raise DomainError(f"cancel из терминального статуса {self.status}")
        for t in self.targets:
            if not t.is_finished:
                t.mark_skipped()
        self.status = SearchStatus.CANCELLED
        self.stage = SearchStage.DONE
        self.finished_at = utcnow()

    def finish(self) -> None:
        unfinished = [t for t in self.targets if not t.is_finished]
        if unfinished:
            raise DomainError(f"finish при {len(unfinished)} незавершённых целях")
        failed = sum(1 for t in self.targets if t.status is TargetStatus.FAILED)
        if failed == len(self.targets):
            self.status = SearchStatus.FAILED
        elif failed:
            self.status = SearchStatus.PARTIAL
        else:
            self.status = SearchStatus.COMPLETED
        self.stage = SearchStage.DONE
        self.finished_at = utcnow()

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def progress(self, fraction: float = 0.0) -> tuple[int, int, int]:
        """Возвращает (targets_total, targets_finished, percent)."""
        total = len(self.targets)
        finished = sum(1 for t in self.targets if t.is_finished)
        frac = min(max(fraction, 0.0), 1.0)
        if self.stage is SearchStage.ANALYZING_QUERY:
            percent = 5
        elif self.stage is SearchStage.COLLECTING:
            percent = int(10 + 70 * (finished / total if total else 0.0))
        elif self.stage is SearchStage.SCORING:
            percent = int(80 + 10 * frac)
        elif self.stage is SearchStage.GROUPING:
            percent = int(90 + 9 * frac)
        else:
            percent = 100
        return total, finished, percent


@dataclass
class Publication:
    platform: str
    source_external_id: str
    post_external_id: str
    url: str
    source_name: str
    source_url: str
    text: str
    title: str | None = None
    published_at: datetime | None = None
    metrics: dict[str, int] | None = None
    is_repost: bool = False
    repost_of_url: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    first_seen_at: datetime = field(default_factory=utcnow)
    last_seen_at: datetime = field(default_factory=utcnow)

    def merge_from(self, other: Publication) -> None:
        """Upsert-логика: обновляем текст/метрики/last_seen_at."""
        self.text = other.text
        self.metrics = other.metrics or self.metrics
        self.title = other.title or self.title
        self.source_name = other.source_name
        self.source_url = other.source_url
        self.url = other.url
        self.published_at = other.published_at or self.published_at
        self.last_seen_at = utcnow()


@dataclass
class SearchResult:
    search_id: uuid.UUID
    publication_id: uuid.UUID
    target_id: uuid.UUID
    relevance: Relevance | None = None
    score: float | None = None
    explanation: str = ""
    region_by_source: bool = False
    region_by_content: bool = False
    region_evidence: str = ""
    sentiment: str | None = None
    excerpt_start: int | None = None
    excerpt_end: int | None = None
    highlights: list[list[int]] = field(default_factory=list)
    group_id: str | None = None
    date_status: DateStatus = DateStatus.UNKNOWN
    excluded: bool = False
    excluded_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def set_score(
        self,
        *,
        relevance: Relevance,
        score: float,
        explanation: str,
        region_by_content: bool,
        region_evidence: str,
        sentiment: str | None,
        excerpt_start: int | None,
        excerpt_end: int | None,
        highlights: list[list[int]],
    ) -> None:
        self.relevance = relevance
        self.score = score
        self.explanation = explanation
        self.region_by_content = region_by_content
        self.region_evidence = region_evidence
        self.sentiment = sentiment
        self.excerpt_start = excerpt_start
        self.excerpt_end = excerpt_end
        self.highlights = highlights

    def set_group(self, group_id: str) -> None:
        self.group_id = group_id

    def set_excluded(self, excluded: bool) -> None:
        self.excluded = excluded
        self.excluded_at = utcnow() if excluded else None

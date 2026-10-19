"""Точка входа search_service.

Поднимает FastAPI (HTTP для ручной проверки + health) и gRPC-сервер (контракт
search.v1). Пока gRPC-транспорт не написан, всю функциональность можно
дёргать через HTTP — см. /docs после запуска.

Архитектурные правила:
- UnitOfWork создаётся из фабрики сессий на каждый вход (async with uow:)
  → параллельные задачи пайплайна не конфликтуют по SQLAlchemy-сессии.
- Pipeline получает фабрики (uow_factory, collector, ml), а не живые объекты.
- SearchRunner — реестр asyncio.Task по search_id; при старте сервиса все
  RUNNING/QUEUED поиски помечаются FAILED с warning «прерван перезапуском».
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from search_service.applications.ports.collector_client import CollectorClient
from search_service.applications.ports.ml_client import MlClient
from search_service.config import Settings
from search_service.domain.entities import (
    Publication,
    Search,
    SearchResult,
    SearchTarget,
    Source,
    utcnow,
)
from search_service.domain.enums import SearchMode, SearchStatus
from search_service.domain.errors import (
    DomainError,
    NotFoundError,
    SearchInvalidParams,
    SearchNotFinished,
    SourceAlreadyExists,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan: bootstrap / teardown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    # 1. БД
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # 2. Клиенты: выбираем реализацию по конфигу
    collector = _make_collector(settings)
    ml = _make_ml(settings)

    # 3. Pipeline + Runner
    from search_service.applications.handlers.pipeline import Pipeline
    from search_service.infra.runner import SearchRunner

    sem = asyncio.Semaphore(settings.collect_concurrency)

    from search_service.infra.database.uow import UnitOfWork

    def uow_factory() -> UnitOfWork:
        # UoW открывает новую сессию на каждый `async with uow:` (см. infra/database/uow.py)
        return UnitOfWork(session_maker)

    pipeline = Pipeline(uow_factory(), collector, ml, sem, settings.target_timeout_sec)
    runner = SearchRunner(pipeline)

    # 4. Восстановление после рестарта: RUNNING/QUEUED → FAILED
    await _mark_interrupted_searches(session_maker)

    # 5. Кладём в app.state — handlers и HTTP-роуты их оттуда достают
    app.state.engine = engine
    app.state.session_maker = session_maker
    app.state.uow_factory = uow_factory
    app.state.collector = collector
    app.state.ml = ml
    app.state.runner = runner
    app.state.pipeline = pipeline

    log.info(
        "search_service started",
        collector_mode=settings.collector_mode,
        ml_mode=settings.ml_mode,
        db=settings.database_url.split("@")[-1] if "@" in settings.database_url else "in-memory",
    )

    try:
        yield
    finally:
        await runner.cancel_all()
        await engine.dispose()
        log.info("search_service stopped")


def _make_collector(settings: Settings) -> CollectorClient:
    if settings.collector_mode == "grpc":
        # Когда напишешь GrpcCollectorClient — раскомментируй:
        # from search_service.infra.collector_client import GrpcCollectorClient
        # return GrpcCollectorClient(settings.collector_grpc)
        raise RuntimeError("GrpcCollectorClient ещё не реализован, используй collector_mode=stub")
    from search_service.infra.collector_stub import StubCollectorClient

    fail = tuple(p for p in settings.stub_fail_platforms.split(",") if p)
    return StubCollectorClient(fail_platforms=fail)


def _make_ml(settings: Settings) -> MlClient:
    if settings.ml_mode == "grpc":
        # from search_service.infra.ml_client import GrpcMlClient
        # return GrpcMlClient(settings.ml_grpc)
        raise RuntimeError("GrpcMlClient ещё не реализован, используй ml_mode=stub")
    from search_service.infra.ml_client import StubMl

    return StubMl()


async def _mark_interrupted_searches(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Все RUNNING/QUEUED на старте → FAILED с warning."""
    from search_service.infra.database.uow import UnitOfWork

    try:
        uow = UnitOfWork(session_maker)
        async with uow:
            orphans = await uow.searches.list_running_or_queued()
            for search in orphans:
                search.status = SearchStatus.FAILED
                search.add_warning("Поиск прерван перезапуском сервиса")
                search.finished_at = utcnow()
                await uow.searches.save(search)
            await uow.commit()
            if orphans:
                log.warning("interrupted searches помечены как FAILED", count=len(orphans))
    except Exception as e:
        # БД может быть ещё не готова на первом запуске до миграций — не падаем
        log.warning("не удалось пометить прерванные поиски", error=str(e))


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="search_service", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    _register_health_routes(app)
    _register_http_api(app)  # HTTP-обёртки над хэндлерами (для демо)
    return app


# ---------------------------------------------------------------------------
# Health-эндпоинты (как в doc3)
# ---------------------------------------------------------------------------
def _register_health_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "search_service"}

    @app.get("/health/db")
    async def health_db() -> dict[str, Any]:
        from sqlalchemy import text

        try:
            async with app.state.session_maker() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(503, f"db error: {e}") from e

    @app.get("/health/redis")
    async def health_redis() -> dict[str, Any]:
        # Redis у search_service напрямую не используется — отвечаем ok
        return {"status": "ok", "note": "not used by search_service directly"}

    @app.get("/health/collector")
    async def health_collector() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": app.state.settings.collector_mode,
            "is_stub": getattr(app.state.collector, "is_stub", False),
        }

    @app.get("/health/ml")
    async def health_ml() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": app.state.settings.ml_mode,
            "is_stub": getattr(app.state.ml, "is_stub", False),
        }


# ---------------------------------------------------------------------------
# HTTP API — обёртки над application-хэндлерами
# Пока gRPC-транспорт не написан, это основной способ дёргать сервис.
# Gateway сможет ходить сюда же, либо переключимся на gRPC без изменения handlers.
# ---------------------------------------------------------------------------
def _register_http_api(app: FastAPI) -> None:
    from pydantic import BaseModel, Field

    # ---------- Sources (B2-02) ----------
    class ResolveReq(BaseModel):
        url: str

    class CreateSourceReq(BaseModel):
        url: str
        name: str | None = None
        is_regional: bool = True
        notes: str = ""

    class UpdateSourceReq(BaseModel):
        name: str | None = None
        is_regional: bool | None = None
        is_active: bool | None = None
        notes: str | None = None

    def _source_dict(s: Source) -> dict[str, Any]:
        return {
            "id": str(s.id),
            "platform": s.platform,
            "external_id": s.external_id,
            "screen_name": s.screen_name,
            "url": s.url,
            "name": s.name,
            "city": s.city,
            "is_regional": s.is_regional,
            "is_active": s.is_active,
            "notes": s.notes,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }

    @app.post("/sources/resolve")
    async def resolve_source(req: ResolveReq) -> dict[str, Any]:
        from search_service.applications.handlers.sources import ResolveRequest, SourceHandler

        uow = app.state.uow_factory()
        handler = SourceHandler(uow, app.state.collector)
        try:
            info, existing = await handler.resolve(ResolveRequest(url=req.url))
        except DomainError as e:
            raise HTTPException(400, str(e)) from e
        return {
            "preview": {
                "platform": info.platform,
                "external_id": info.external_id,
                "url": info.url,
                "name": info.name,
                "city": info.city,
                "members_count": info.members_count,
                "existing_source_id": str(existing.id) if existing else None,
            }
        }

    @app.post("/sources")
    async def create_source(req: CreateSourceReq) -> dict[str, Any]:
        from search_service.applications.handlers.sources import CreateRequest, SourceHandler

        uow = app.state.uow_factory()
        handler = SourceHandler(uow, app.state.collector)
        try:
            source = await handler.create(CreateRequest(**req.model_dump()))
        except SourceAlreadyExists as e:
            raise HTTPException(409, "SOURCE_ALREADY_EXISTS") from e
        except DomainError as e:
            raise HTTPException(400, str(e)) from e
        return {"source": _source_dict(source)}

    @app.get("/sources")
    async def list_sources(
        platforms: str | None = None,
        q: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        from search_service.applications.handlers.sources import ListRequest, SourceHandler

        uow = app.state.uow_factory()
        handler = SourceHandler(uow, app.state.collector)
        platforms_list = [p for p in (platforms or "").split(",") if p] or None
        sources, total, has_more = await handler.list(
            ListRequest(
                platforms=platforms_list, q=q, is_active=is_active, limit=limit, offset=offset
            )
        )
        return {
            "sources": [_source_dict(s) for s in sources],
            "total": total,
            "has_more": has_more,
        }

    @app.patch("/sources/{source_id}")
    async def update_source(source_id: uuid.UUID, req: UpdateSourceReq) -> dict[str, Any]:
        from search_service.applications.handlers.sources import SourceHandler, UpdateRequest

        uow = app.state.uow_factory()
        handler = SourceHandler(uow, app.state.collector)
        try:
            source = await handler.update(UpdateRequest(source_id=source_id, **req.model_dump()))
        except NotFoundError as e:
            raise HTTPException(404, "SOURCE_NOT_FOUND") from e
        return {"source": _source_dict(source)}

    @app.delete("/sources/{source_id}")
    async def delete_source(source_id: uuid.UUID) -> dict[str, Any]:
        from search_service.applications.handlers.sources import DeleteRequest, SourceHandler

        uow = app.state.uow_factory()
        handler = SourceHandler(uow, app.state.collector)
        try:
            await handler.delete(DeleteRequest(source_id=source_id))
        except NotFoundError as e:
            raise HTTPException(404, "SOURCE_NOT_FOUND") from e
        return {}

    # ---------- Search (B2-03, B2-09) ----------
    class StartSearchReq(BaseModel):
        query: str
        period_from: str
        period_to: str
        mode: SearchMode = SearchMode.SELECTED
        platforms: list[str] = Field(default_factory=list)
        source_ids: list[str] = Field(default_factory=list)

    def _search_dict(s: Search) -> dict[str, Any]:
        return {
            "id": str(s.id),
            "status": s.status,
            "stage": s.stage,
            "progress": {
                "targets_total": len(s.targets) if hasattr(s, "targets") and s.targets else 0,
                "targets_finished": sum(1 for t in (s.targets or []) if t.is_finished),
                "percent": s.progress()[2] if hasattr(s, "progress") else 0,
            },
            "params": {
                "query": s.query,
                "query_type": s.query_type,
                "period_from": s.period.from_date.isoformat(),
                "period_to": s.period.to_date.isoformat(),
                "mode": s.mode,
                "platforms": s.platforms,
                "source_ids": [str(x) for x in s.source_ids],
            },
            "query_analysis": s.query_analysis,
            "warnings": s.warnings,
            "created_at": s.created_at.isoformat(),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        }

    def _target_dict(t: SearchTarget) -> dict[str, Any]:
        return {
            "id": str(t.id),
            "kind": t.kind,
            "platform": t.platform,
            "source_id": str(t.source_id) if t.source_id else None,
            "name": t.name,
            "url": t.url,
            "status": t.status,
            "fetched": t.fetched,
            "matched": t.matched,
            "attempts": t.attempts,
            "error": {"code": t.error_code, "message": t.error_message} if t.error_code else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        }

    @app.post("/searches")
    async def start_search(req: StartSearchReq) -> dict[str, Any]:
        from search_service.applications.handlers.searches import SearchHandler, StartSearchRequest

        uow = app.state.uow_factory()
        handler = SearchHandler(uow, app.state.runner)
        try:
            search = await handler.start(
                StartSearchRequest(
                    query=req.query,
                    period_from=req.period_from,
                    period_to=req.period_to,
                    mode=req.mode,
                    platforms=req.platforms,
                    source_ids=[uuid.UUID(x) for x in req.source_ids],
                )
            )
        except SearchInvalidParams as e:
            raise HTTPException(
                400, {"code": "SEARCH_INVALID_PARAMS", "field": e.field, "message": e.message}
            ) from e
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        except DomainError as e:
            raise HTTPException(400, str(e)) from e
        # перечитаем с targets
        search_full = await handler.get(search.id)
        return {
            "search": {
                **_search_dict(search_full),
                "targets": [_target_dict(t) for t in search_full.targets],
            }
        }

    @app.get("/searches")
    async def list_searches(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        from search_service.applications.handlers.searches import SearchHandler

        uow = app.state.uow_factory()
        handler = SearchHandler(uow, app.state.runner)
        searches, total, has_more = await handler.list(limit=limit, offset=offset)
        return {
            "searches": [_search_dict(s) for s in searches],
            "total": total,
            "has_more": has_more,
        }

    @app.get("/searches/{search_id}")
    async def get_search(search_id: uuid.UUID) -> dict[str, Any]:
        from search_service.applications.handlers.searches import SearchHandler

        uow = app.state.uow_factory()
        handler = SearchHandler(uow, app.state.runner)
        try:
            search = await handler.get(search_id)
        except NotFoundError as e:
            raise HTTPException(404, "SEARCH_NOT_FOUND") from e
        return {
            "search": {**_search_dict(search), "targets": [_target_dict(t) for t in search.targets]}
        }

    @app.post("/searches/{search_id}/cancel")
    async def cancel_search(search_id: uuid.UUID) -> dict[str, Any]:
        from search_service.applications.handlers.control import ControlHandler

        uow = app.state.uow_factory()
        handler = ControlHandler(uow, app.state.runner)
        try:
            search = await handler.cancel(search_id)
        except NotFoundError as e:
            raise HTTPException(404, "SEARCH_NOT_FOUND") from e
        return {"search": _search_dict(search)}

    class RetryReq(BaseModel):
        target_ids: list[str] | None = None

    @app.post("/searches/{search_id}/retry")
    async def retry_search(search_id: uuid.UUID, req: RetryReq) -> dict[str, Any]:
        from search_service.applications.handlers.control import ControlHandler

        uow = app.state.uow_factory()
        handler = ControlHandler(uow, app.state.runner)
        try:
            search = await handler.retry(
                search_id,
                [uuid.UUID(x) for x in req.target_ids] if req.target_ids else None,
            )
        except NotFoundError as e:
            raise HTTPException(404, "SEARCH_NOT_FOUND") from e
        except SearchNotFinished as e:
            raise HTTPException(409, "SEARCH_NOT_FINISHED") from e
        return {"search": _search_dict(search)}

    # ---------- Results (B2-07, B2-09) ----------
    @app.get("/searches/{search_id}/results")
    async def list_results(
        search_id: uuid.UUID,
        relevance: str | None = None,
        platforms: str | None = None,
        include_excluded: bool = False,
        sort: str = "relevance",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        from search_service.applications.handlers.results import ResultFilter, ResultsHandler

        uow = app.state.uow_factory()
        handler = ResultsHandler(uow)
        f = ResultFilter(
            relevance=[r for r in (relevance or "").split(",") if r] or None,
            platforms=[p for p in (platforms or "").split(",") if p] or None,
            include_excluded=include_excluded,
        )
        try:
            results, total, has_more, counts = await handler.list_results(
                search_id, f, sort=sort, limit=limit, offset=offset
            )
        except NotFoundError as e:
            raise HTTPException(404, "SEARCH_NOT_FOUND") from e

        # обогатим результата публикацией
        async with uow:
            pub_ids = [r.publication_id for r in results]
            pubs = await uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}
        return {
            "results": [_result_with_pub(r, pubs_by_id.get(r.publication_id)) for r in results],
            "total": total,
            "has_more": has_more,
            "counts": counts,
        }

    class SetExcludedReq(BaseModel):
        result_ids: list[str]
        excluded: bool

    @app.post("/searches/{search_id}/set_excluded")
    async def set_excluded(search_id: uuid.UUID, req: SetExcludedReq) -> dict[str, Any]:
        from search_service.applications.handlers.control import ControlHandler

        uow = app.state.uow_factory()
        handler = ControlHandler(uow, app.state.runner)
        try:
            counts = await handler.set_excluded(
                search_id, [uuid.UUID(x) for x in req.result_ids], req.excluded
            )
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return {"counts": counts}

    # ---------- Export (B2-08) ----------
    @app.get("/searches/{search_id}/export.xlsx")
    async def export_xlsx(
        search_id: uuid.UUID,
        relevance: str | None = None,
        platforms: str | None = None,
        include_excluded: bool = False,
        sort: str = "relevance",
    ) -> Response:
        from search_service.applications.handlers.export import ExportHandler
        from search_service.applications.handlers.results import ResultFilter

        uow = app.state.uow_factory()
        handler = ExportHandler(uow)
        f = ResultFilter(
            relevance=[r for r in (relevance or "").split(",") if r] or None,
            platforms=[p for p in (platforms or "").split(",") if p] or None,
            include_excluded=include_excluded,
        )
        try:
            content, filename, mime = await handler.to_xlsx(search_id, f, sort=sort)
        except NotFoundError as e:
            raise HTTPException(404, "SEARCH_NOT_FOUND") from e
        return Response(
            content=content,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def _result_with_pub(r: SearchResult, pub: Publication | None) -> dict[str, Any]:
    """Собираем Result-представление для HTTP-ответа (то же, что уйдёт в gRPC)."""
    if pub is None:
        return {"id": str(r.id)}
    title = pub.title
    title_source = "title"
    if not title:
        text = pub.text.strip()
        title_source = "post_start"
        if len(text) <= 120:
            title = text
        else:
            cut = text[:120]
            last_space = cut.rfind(" ")
            if last_space > 60:
                cut = cut[:last_space]
            title = cut + "…"

    excerpt = ""
    excerpt_parts = []
    if pub and r.excerpt_start is not None and r.excerpt_end is not None:
        excerpt = pub.text[r.excerpt_start : r.excerpt_end]
        # нарезка по highlights внутри выдержки
        for span in r.highlights:
            if len(span) != 2:
                continue
            a, b = span
            # пересечение с [excerpt_start, excerpt_end]
            lo = max(a, r.excerpt_start)
            hi = min(b, r.excerpt_end)
            if lo < hi:
                excerpt_parts.append(
                    {
                        "text": pub.text[lo:hi],
                        "highlight": True,
                        "start": lo - r.excerpt_start,
                        "end": hi - r.excerpt_start,
                    }
                )

    return {
        "id": str(r.id),
        "publication_id": str(r.publication_id),
        "platform": pub.platform,
        "source": {
            "name": pub.source_name,
            "url": pub.source_url,
            "is_regional": r.region_by_source,
        },
        "url": pub.url,
        "title": title,
        "title_source": title_source,
        "excerpt": excerpt,
        "excerpt_parts": excerpt_parts,
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
        "date_status": r.date_status,
        "relevance": r.relevance,
        "score": r.score,
        "explanation": r.explanation,
        "sentiment": r.sentiment,
        "region": {
            "by_source": r.region_by_source,
            "by_content": r.region_by_content,
            "evidence": r.region_evidence,
        },
        "group_id": r.group_id,
        "metrics": pub.metrics,
        "excluded": r.excluded,
        "found_by_target_id": str(r.target_id),
    }


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = Settings()
    uvicorn.run("search_service.main:app", host="0.0.0.0", port=s.http_port, reload=False)

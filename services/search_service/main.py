from __future__ import annotations
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from search_service.config import Settings
from search_service.infra.db.uow import UnitOfWork
from search_service.infra.runner import SearchRunner
from search_service.applications.handlers.pipeline import Pipeline


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # bootstrap
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def uow_factory():
        return UnitOfWork(Session())

    # клиенты (заглушки — потом подставим реальные gRPC)
    from search_service.src.search_service.infra.collector_client import StubCollector
    from search_service.src.search_service.infra.ml_client import StubMl
    collector = StubCollector()
    ml = StubMl()

    sem = asyncio.Semaphore(settings.collect_concurrency)
    pipeline = Pipeline(uow_factory, collector, ml, sem, settings.target_timeout_sec)
    runner = SearchRunner(pipeline)

    # восстанавливаем прерванные поиски
    async with Session() as s:
        uow = UnitOfWork(s)
        async with uow:
            orphans = await uow.searches.list_running_or_queued()
            for search in orphans:
                search.status = "failed"
                search.add_warning("Поиск прерван перезапуском сервиса")
                await uow.searches.save(search)
            await uow.commit()

    app.state.runner = runner
    app.state.uow_factory = uow_factory
    app.state.collector = collector
    app.state.ml = ml

    yield

    await runner.cancel_all()
    await engine.dispose()


app = FastAPI(title="search_service", lifespan=lifespan)


@app.get("/health")
async def health(): return {"status": "ok"}
from __future__ import annotations
import uuid
from dataclasses import dataclass

from search_service.domain.entities import Source
from search_service.domain.errors import NotFoundError, SourceAlreadyExists, DomainError
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.ports.collector_client import CollectorClient


@dataclass
class ResolveRequest:
    url: str

@dataclass
class CreateRequest:
    url: str
    name: str | None = None
    is_regional: bool = True
    notes: str = ""

@dataclass
class ListRequest:
    platforms: list[str] | None = None
    q: str | None = None
    is_active: bool | None = None
    limit: int = 50
    offset: int = 0

@dataclass
class UpdateRequest:
    source_id: uuid.UUID
    name: str | None = None
    is_regional: bool | None = None
    is_active: bool | None = None
    notes: str | None = None

@dataclass
class DeleteRequest:
    source_id: uuid.UUID


class SourceHandler:
    def __init__(self, uow: UnitOfWork, collector: CollectorClient):
        self.uow = uow
        self.collector = collector

    async def resolve(self, req: ResolveRequest):
        info = await self.collector.resolve_source(req.url)
        async with self.uow:
            existing = await self.uow.sources.get_by_key(info.platform, info.external_id)
            return info, existing

    async def create(self, req: CreateRequest) -> Source:
        info = await self.collector.resolve_source(req.url)
        if info.is_closed:
            raise DomainError("SOURCE_PRIVATE")
        name = req.name or info.name or info.screen_name
        async with self.uow:
            existing = await self.uow.sources.get_by_key(info.platform, info.external_id)
            if existing and existing.is_alive:
                raise SourceAlreadyExists(f"{info.platform}:{info.external_id}")
            source = Source(
                platform=info.platform,
                external_id=info.external_id,
                screen_name=info.screen_name,
                url=info.url,
                name=name,
                city=info.city,
                is_regional=req.is_regional,
                notes=req.notes,
            )
            await self.uow.sources.add(source)
            await self.uow.commit()
            return source

    async def list(self, req: ListRequest):
        limit = max(1, min(req.limit or 50, 200))
        async with self.uow:
            sources, total = await self.uow.sources.list(
                platforms=req.platforms, q=req.q,
                is_active=req.is_active, limit=limit, offset=req.offset,
            )
            return sources, total, req.offset + len(sources) < total

    async def update(self, req: UpdateRequest) -> Source:
        async with self.uow:
            source = await self.uow.sources.get_by_id(req.source_id)
            if not source or not source.is_alive:
                raise NotFoundError("SOURCE_NOT_FOUND")
            updates = {k: v for k, v in req.__dict__.items() if k != "source_id" and v is not None}
            source.update(**updates)
            await self.uow.sources.save(source)
            await self.uow.commit()
            return source

    async def delete(self, req: DeleteRequest) -> None:
        async with self.uow:
            source = await self.uow.sources.get_by_id(req.source_id)
            if not source or not source.is_alive:
                raise NotFoundError("SOURCE_NOT_FOUND")
            source.soft_delete()
            await self.uow.sources.save(source)
            await self.uow.commit()
from __future__ import annotations
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.ports.collector_client import CollectorClient, SourceInfo, CollectResult, RawPost
from search_service.applications.ports.ml_client import MlClient, QueryAnalysis, PostScore, PostGroup
from search_service.domain.entities import Source, Search, SearchTarget, Publication, SearchResult
from search_service.domain.enums import Relevance
from search_service.domain.value_objects import Period


class InMemorySources:
    def __init__(self): self.store: dict[uuid.UUID, Source] = {}
    async def get_by_id(self, i): return self.store.get(i)
    async def get_by_key(self, p, e):
        for s in self.store.values():
            if s.platform == p and s.external_id == e and s.is_alive: return s
        return None
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]
    async def list(self, **kw): items = [s for s in self.store.values() if s.is_alive]; return items, len(items)
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e


class InMemorySearches:
    def __init__(self): self.store: dict[uuid.UUID, Search] = {}
    async def get_by_id(self, i): return self.store.get(i)
    async def get_with_targets(self, i): return self.store.get(i)
    async def list(self, **kw): items = list(self.store.values()); return items, len(items), False
    async def list_running_or_queued(self):
        return [s for s in self.store.values() if s.status in {"queued", "running"}]
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e


class InMemoryTargets:
    def __init__(self): self.store: dict[uuid.UUID, SearchTarget] = {}
    async def list_by_search(self, sid): return [t for t in self.store.values() if t.search_id == sid]
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]


class InMemoryPublications:
    def __init__(self): self.store: dict[uuid.UUID, Publication] = {}
    async def get_by_key(self, p, s, post):
        for pub in self.store.values():
            if pub.platform == p and pub.source_external_id == s and pub.post_external_id == post:
                return pub
        return None
    async def get_by_ids(self, ids): return [self.store[i] for i in ids if i in self.store]
    async def upsert(self, e):
        existing = await self.get_by_key(e.platform, e.source_external_id, e.post_external_id)
        if existing:
            existing.merge_from(e)
            return existing
        self.store[e.id] = e
        return e


class InMemoryResults:
    def __init__(self): self.store: dict[uuid.UUID, SearchResult] = {}
    async def add(self, e): self.store[e.id] = e
    async def save(self, e): self.store[e.id] = e
    async def get_by_search(self, sid): return [r for r in self.store.values() if r.search_id == sid]
    async def list_filtered(self, **kw):
        items = [r for r in self.store.values() if r.search_id == kw["search_id"] and r.relevance is not None]
        return items, len(items), False
    async def counts(self, sid):
        items = [r for r in self.store.values() if r.search_id == sid]
        return {
            "total": sum(1 for r in items if r.relevance in {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED} and not r.excluded),
            "direct": sum(1 for r in items if r.relevance == Relevance.DIRECT and not r.excluded),
            "indirect": sum(1 for r in items if r.relevance == Relevance.INDIRECT and not r.excluded),
            "disputed": sum(1 for r in items if r.relevance == Relevance.DISPUTED and not r.excluded),
            "rejected": sum(1 for r in items if r.relevance == Relevance.IRRELEVANT),
            "excluded": sum(1 for r in items if r.excluded),
            "unknown_date": 0,
            "groups": len({r.group_id for r in items if r.group_id}),
        }
    async def exists_in_search(self, sid, pid):
        return any(r.search_id == sid and r.publication_id == pid for r in self.store.values())


class InMemoryUoW:
    def __init__(self):
        self.sources = InMemorySources()
        self.searches = InMemorySearches()
        self.targets = InMemoryTargets()
        self.publications = InMemoryPublications()
        self.results = InMemoryResults()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def commit(self): pass
    async def rollback(self): pass
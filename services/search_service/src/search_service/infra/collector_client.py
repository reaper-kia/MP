from search_service.applications.ports.collector_client import CollectResult, SourceInfo


class StubCollector:
    """Реализация CollectorClient, возвращает пустые ответы. Позже заменим на gRPC."""

    async def resolve_source(self, url: str) -> SourceInfo:
        raise NotImplementedError("collector service not wired yet")

    async def collect_from_source(self, **kw) -> CollectResult:
        return CollectResult(posts=[], truncated=False, warnings=[])

    async def search_platform(self, **kw) -> CollectResult:
        return CollectResult(posts=[], truncated=False, warnings=[])

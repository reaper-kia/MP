"""proto → команда → mediator → proto. Логики и try/except здесь нет (ошибки — @grpc_errors)."""

from search.v1 import search_service_pb2 as pb
from search.v1 import search_service_pb2_grpc as pb_grpc

from search_service.applications.commands.results import SetExcludedCommand
from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.commands.sources import (
    CreateSourceCommand,
    DeleteSourceCommand,
    ImportSourcesCommand,
    UpdateSourceCommand,
)
from search_service.applications.exceptions import (
    ResultNotFoundError,
    SearchNotFoundError,
    SourceNotFoundError,
)
from search_service.applications.mediator import Mediator
from search_service.applications.queries.results import (
    ExportSearchQuery,
    ListGroupsQuery,
    ListResultsQuery,
)
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.queries.sources import ListSourcesQuery, ResolveSourceQuery
from search_service.transport.grpc.errors import Context, grpc_errors
from search_service.transport.grpc.mappers import (
    context_from_proto,
    counts_to_proto,
    filter_from_proto,
    format_from_proto,
    group_to_proto,
    import_report_to_proto,
    mode_from_proto,
    parse_date,
    parse_uuid,
    parse_uuids,
    platforms_from_proto,
    preview_to_proto,
    result_to_proto,
    search_to_proto,
    sort_from_proto,
    source_to_proto,
)

DEFAULT_LIMIT = 50


class SearchServicer(pb_grpc.SearchServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    # ───────────────────────── источники ─────────────────────────

    @grpc_errors
    async def ResolveSource(
        self, request: pb.ResolveSourceRequest, context: Context
    ) -> pb.ResolveSourceResponse:
        preview = await self._mediator.send(
            ResolveSourceQuery(ctx=context_from_proto(request.context), url=request.url)
        )
        return pb.ResolveSourceResponse(preview=preview_to_proto(preview))

    @grpc_errors
    async def CreateSource(
        self, request: pb.CreateSourceRequest, context: Context
    ) -> pb.CreateSourceResponse:
        source = await self._mediator.send(
            CreateSourceCommand(
                ctx=context_from_proto(request.context),
                url=request.url,
                name=request.name if request.HasField("name") else None,
                is_regional=request.is_regional,
                notes=request.notes,
            )
        )
        return pb.CreateSourceResponse(source=source_to_proto(source))

    @grpc_errors
    async def ListSources(
        self, request: pb.ListSourcesRequest, context: Context
    ) -> pb.ListSourcesResponse:
        page = await self._mediator.send(
            ListSourcesQuery(
                ctx=context_from_proto(request.context),
                platforms=platforms_from_proto(request.platforms),
                q=request.q,
                is_active=request.is_active if request.HasField("is_active") else None,
                limit=request.limit or DEFAULT_LIMIT,
                offset=request.offset,
            )
        )
        return pb.ListSourcesResponse(
            sources=[source_to_proto(s) for s in page.items],
            total=page.total,
            has_more=page.has_more,
        )

    @grpc_errors
    async def UpdateSource(
        self, request: pb.UpdateSourceRequest, context: Context
    ) -> pb.UpdateSourceResponse:
        source = await self._mediator.send(
            UpdateSourceCommand(
                ctx=context_from_proto(request.context),
                source_id=parse_uuid(request.source_id, SourceNotFoundError),
                name=request.name if request.HasField("name") else None,
                is_regional=request.is_regional if request.HasField("is_regional") else None,
                is_active=request.is_active if request.HasField("is_active") else None,
                notes=request.notes if request.HasField("notes") else None,
            )
        )
        return pb.UpdateSourceResponse(source=source_to_proto(source))

    @grpc_errors
    async def DeleteSource(
        self, request: pb.DeleteSourceRequest, context: Context
    ) -> pb.DeleteSourceResponse:
        await self._mediator.send(
            DeleteSourceCommand(
                ctx=context_from_proto(request.context),
                source_id=parse_uuid(request.source_id, SourceNotFoundError),
            )
        )
        return pb.DeleteSourceResponse()

    @grpc_errors
    async def ImportSources(
        self, request: pb.ImportSourcesRequest, context: Context
    ) -> pb.ImportSourcesResponse:
        report = await self._mediator.send(
            ImportSourcesCommand(ctx=context_from_proto(request.context), xlsx=request.xlsx)
        )
        return import_report_to_proto(report)

    # ───────────────────────── поиск ─────────────────────────

    @grpc_errors
    async def StartSearch(
        self, request: pb.StartSearchRequest, context: Context
    ) -> pb.StartSearchResponse:
        search = await self._mediator.send(
            StartSearchCommand(
                ctx=context_from_proto(request.context),
                query=request.query,
                period_from=parse_date(request.period_from, "period_from"),
                period_to=parse_date(request.period_to, "period_to"),
                mode=mode_from_proto(request.mode),
                platforms=platforms_from_proto(request.platforms),
                source_ids=parse_uuids(request.source_ids, "source_ids"),
                fresh=request.fresh,
            )
        )
        return pb.StartSearchResponse(search=search_to_proto(search))

    @grpc_errors
    async def GetSearch(
        self, request: pb.GetSearchRequest, context: Context
    ) -> pb.GetSearchResponse:
        search = await self._mediator.send(
            GetSearchQuery(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
            )
        )
        return pb.GetSearchResponse(search=search_to_proto(search))

    @grpc_errors
    async def ListSearches(
        self, request: pb.ListSearchesRequest, context: Context
    ) -> pb.ListSearchesResponse:
        page = await self._mediator.send(
            ListSearchesQuery(
                ctx=context_from_proto(request.context),
                limit=request.limit or 20,
                offset=request.offset,
            )
        )
        return pb.ListSearchesResponse(
            searches=[search_to_proto(s) for s in page.items], has_more=page.has_more
        )

    @grpc_errors
    async def RetrySearch(
        self, request: pb.RetrySearchRequest, context: Context
    ) -> pb.RetrySearchResponse:
        search = await self._mediator.send(
            RetrySearchCommand(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
                target_ids=parse_uuids(request.target_ids, "target_ids"),
            )
        )
        return pb.RetrySearchResponse(search=search_to_proto(search))

    @grpc_errors
    async def CancelSearch(
        self, request: pb.CancelSearchRequest, context: Context
    ) -> pb.CancelSearchResponse:
        search = await self._mediator.send(
            CancelSearchCommand(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
            )
        )
        return pb.CancelSearchResponse(search=search_to_proto(search))

    # ───────────────────────── подборка ─────────────────────────

    @grpc_errors
    async def ListResults(
        self, request: pb.ListResultsRequest, context: Context
    ) -> pb.ListResultsResponse:
        page = await self._mediator.send(
            ListResultsQuery(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
                filter=filter_from_proto(request.filter),
                sort=sort_from_proto(request.sort),
                limit=request.limit or DEFAULT_LIMIT,
                offset=request.offset,
            )
        )
        return pb.ListResultsResponse(
            results=[result_to_proto(r) for r in page.items],
            total=page.total,
            has_more=page.has_more,
        )

    @grpc_errors
    async def ListGroups(
        self, request: pb.ListGroupsRequest, context: Context
    ) -> pb.ListGroupsResponse:
        page = await self._mediator.send(
            ListGroupsQuery(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
                filter=filter_from_proto(request.filter),
                limit=request.limit or DEFAULT_LIMIT,
                offset=request.offset,
            )
        )
        return pb.ListGroupsResponse(
            groups=[group_to_proto(g) for g in page.items],
            total=page.total,
            has_more=page.has_more,
        )

    @grpc_errors
    async def SetExcluded(
        self, request: pb.SetExcludedRequest, context: Context
    ) -> pb.SetExcludedResponse:
        counts = await self._mediator.send(
            SetExcludedCommand(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
                result_ids=[parse_uuid(r, ResultNotFoundError) for r in request.result_ids],
                excluded=request.excluded,
            )
        )
        return pb.SetExcludedResponse(counts=counts_to_proto(counts))

    @grpc_errors
    async def ExportSearch(
        self, request: pb.ExportSearchRequest, context: Context
    ) -> pb.ExportSearchResponse:
        file = await self._mediator.send(
            ExportSearchQuery(
                ctx=context_from_proto(request.context),
                search_id=parse_uuid(request.search_id, SearchNotFoundError),
                format=format_from_proto(request.format),
                filter=filter_from_proto(request.filter),
                sort=sort_from_proto(request.sort),
            )
        )
        return pb.ExportSearchResponse(
            content=file.content, filename=file.filename, mime_type=file.mime_type
        )

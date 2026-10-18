from contracts.common.v1 import common_pb2
from contracts.example.v1 import example_pb2 as pb
from contracts.example.v1 import example_pb2_grpc as pb_grpc
from example_service.application.commands.items import CreateItem, DeleteItem, UpdateItem
from example_service.application.queries.items import GetItem, ListItems
from example_service.transport.grpc.mappers import item_to_pb, parse_uuid, status_from_pb
from platform_common.context import RequestContext
from platform_common.grpc.errors import ServicerContext, rpc
from platform_common.mediator import Mediator


class ExampleServicer(pb_grpc.ExampleServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._m = mediator

    @rpc
    async def CreateItem(
        self, request: pb.CreateItemRequest, context: ServicerContext
    ) -> pb.CreateItemResponse:
        item = await self._m.send(
            CreateItem(
                RequestContext.from_proto(request.context), request.title, request.description
            )
        )
        return pb.CreateItemResponse(item=item_to_pb(item))

    @rpc
    async def GetItem(
        self, request: pb.GetItemRequest, context: ServicerContext
    ) -> pb.GetItemResponse:
        item = await self._m.send(
            GetItem(
                RequestContext.from_proto(request.context), parse_uuid(request.item_id, "item_id")
            )
        )
        return pb.GetItemResponse(item=item_to_pb(item))

    @rpc
    async def ListItems(
        self, request: pb.ListItemsRequest, context: ServicerContext
    ) -> pb.ListItemsResponse:
        page = await self._m.send(
            ListItems(
                RequestContext.from_proto(request.context),
                limit=request.page.limit,
                cursor=request.page.cursor,
                status=status_from_pb(request.status),
            )
        )
        return pb.ListItemsResponse(
            items=[item_to_pb(i) for i in page.items],
            page=common_pb2.PageInfo(next_cursor=page.next_cursor),
        )

    @rpc
    async def UpdateItem(
        self, request: pb.UpdateItemRequest, context: ServicerContext
    ) -> pb.UpdateItemResponse:
        item = await self._m.send(
            UpdateItem(
                RequestContext.from_proto(request.context),
                parse_uuid(request.item_id, "item_id"),
                title=request.title if request.HasField("title") else None,
                description=request.description if request.HasField("description") else None,
                status=status_from_pb(request.status),
            )
        )
        return pb.UpdateItemResponse(item=item_to_pb(item))

    @rpc
    async def DeleteItem(
        self, request: pb.DeleteItemRequest, context: ServicerContext
    ) -> pb.DeleteItemResponse:
        await self._m.send(
            DeleteItem(
                RequestContext.from_proto(request.context), parse_uuid(request.item_id, "item_id")
            )
        )
        return pb.DeleteItemResponse()

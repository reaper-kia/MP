from example.v1 import example_service_pb2 as pb
from example.v1 import example_service_pb2_grpc as pb_grpc

from example_service.applications.commands.create_item import CreateItemCommand
from example_service.applications.commands.delete_item import DeleteItemCommand
from example_service.applications.commands.update_item import UpdateItemCommand
from example_service.applications.mediator import Mediator
from example_service.applications.queries.get_item import GetItemQuery
from example_service.applications.queries.list_items import ListItemsQuery
from example_service.transport.grpc.errors import Context, grpc_errors
from example_service.transport.grpc.mappers import (
    STATUS_FROM_PROTO,
    context_from_proto,
    item_to_proto,
    parse_item_id,
)


class ExampleServicer(pb_grpc.ExampleServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    @grpc_errors
    async def CreateItem(
        self, request: pb.CreateItemRequest, context: Context
    ) -> pb.CreateItemResponse:
        item = await self._mediator.send(
            CreateItemCommand(
                ctx=context_from_proto(request.context),
                title=request.title,
                description=request.description,
            )
        )
        return pb.CreateItemResponse(item=item_to_proto(item))

    @grpc_errors
    async def GetItem(self, request: pb.GetItemRequest, context: Context) -> pb.GetItemResponse:
        item = await self._mediator.send(
            GetItemQuery(
                ctx=context_from_proto(request.context), item_id=parse_item_id(request.item_id)
            )
        )
        return pb.GetItemResponse(item=item_to_proto(item))

    @grpc_errors
    async def ListItems(
        self, request: pb.ListItemsRequest, context: Context
    ) -> pb.ListItemsResponse:
        page = await self._mediator.send(
            ListItemsQuery(
                ctx=context_from_proto(request.context),
                limit=request.limit or 20,
                offset=request.offset,
            )
        )
        return pb.ListItemsResponse(
            items=[item_to_proto(i) for i in page.items], has_more=page.has_more
        )

    @grpc_errors
    async def UpdateItem(
        self, request: pb.UpdateItemRequest, context: Context
    ) -> pb.UpdateItemResponse:
        item = await self._mediator.send(
            UpdateItemCommand(
                ctx=context_from_proto(request.context),
                item_id=parse_item_id(request.item_id),
                title=request.title if request.HasField("title") else None,
                description=request.description if request.HasField("description") else None,
                status=STATUS_FROM_PROTO.get(request.status),  # UNSPECIFIED → None
            )
        )
        return pb.UpdateItemResponse(item=item_to_proto(item))

    @grpc_errors
    async def DeleteItem(
        self, request: pb.DeleteItemRequest, context: Context
    ) -> pb.DeleteItemResponse:
        await self._mediator.send(
            DeleteItemCommand(
                ctx=context_from_proto(request.context), item_id=parse_item_id(request.item_id)
            )
        )
        return pb.DeleteItemResponse()

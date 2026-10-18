from contracts.common.v1 import common_pb2
from contracts.{{name}}.v1 import {{name}}_pb2 as pb
from contracts.{{name}}.v1 import {{name}}_pb2_grpc as pb_grpc
from platform_common.context import RequestContext
from platform_common.grpc.errors import ServicerContext, rpc
from platform_common.mediator import Mediator

from {{name}}_service.application.commands import Create{{Entity}}
from {{name}}_service.application.queries import Get{{Entity}}, List{{Entities}}
from {{name}}_service.transport.grpc.mappers import {{entity}}_to_pb, parse_uuid


class {{Name}}Servicer(pb_grpc.{{Name}}ServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._m = mediator

    @rpc
    async def Create{{Entity}}(
        self, request: pb.Create{{Entity}}Request, context: ServicerContext
    ) -> pb.Create{{Entity}}Response:
        {{entity}} = await self._m.send(
            Create{{Entity}}(RequestContext.from_proto(request.context), request.title)
        )
        return pb.Create{{Entity}}Response({{entity}}={{entity}}_to_pb({{entity}}))

    @rpc
    async def Get{{Entity}}(
        self, request: pb.Get{{Entity}}Request, context: ServicerContext
    ) -> pb.Get{{Entity}}Response:
        {{entity}} = await self._m.send(
            Get{{Entity}}(
                RequestContext.from_proto(request.context),
                parse_uuid(request.{{entity}}_id, "{{entity}}_id"),
            )
        )
        return pb.Get{{Entity}}Response({{entity}}={{entity}}_to_pb({{entity}}))

    @rpc
    async def List{{Entities}}(
        self, request: pb.List{{Entities}}Request, context: ServicerContext
    ) -> pb.List{{Entities}}Response:
        page = await self._m.send(
            List{{Entities}}(
                RequestContext.from_proto(request.context),
                limit=request.page.limit,
                cursor=request.page.cursor,
            )
        )
        return pb.List{{Entities}}Response(
            {{entities}}=[{{entity}}_to_pb(x) for x in page.{{entities}}],
            page=common_pb2.PageInfo(next_cursor=page.next_cursor),
        )

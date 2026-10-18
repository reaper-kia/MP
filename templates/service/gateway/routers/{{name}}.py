from typing import Annotated
from uuid import UUID

from contracts.common.v1 import common_pb2
from contracts.{{name}}.v1 import {{name}}_pb2 as pb
from fastapi import APIRouter, Query, status

from gateway.dependencies import AuthCtx, Clients
from gateway.schemas.{{name}} import {{Entity}}CreateIn, {{Entity}}Out
from gateway.schemas.common import ERRORS, Page

router = APIRouter(prefix="/api/v1/{{url}}", tags=["{{name}}"], responses=ERRORS)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_{{entity}}(body: {{Entity}}CreateIn, ctx: AuthCtx, clients: Clients) -> {{Entity}}Out:
    resp = await clients.{{name}}.Create{{Entity}}(pb.Create{{Entity}}Request(context=ctx, title=body.title))
    return {{Entity}}Out.from_pb(resp.{{entity}})


@router.get("")
async def list_{{entities}}(
    ctx: AuthCtx,
    clients: Clients,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str = "",
) -> Page[{{Entity}}Out]:
    resp = await clients.{{name}}.List{{Entities}}(
        pb.List{{Entities}}Request(context=ctx, page=common_pb2.PageRequest(limit=limit, cursor=cursor))
    )
    return Page[{{Entity}}Out](
        items=[{{Entity}}Out.from_pb(x) for x in resp.{{entities}}],
        next_cursor=resp.page.next_cursor or None,
    )


@router.get("/{{{entity}}_id}")
async def get_{{entity}}({{entity}}_id: UUID, ctx: AuthCtx, clients: Clients) -> {{Entity}}Out:
    resp = await clients.{{name}}.Get{{Entity}}(
        pb.Get{{Entity}}Request(context=ctx, {{entity}}_id=str({{entity}}_id))
    )
    return {{Entity}}Out.from_pb(resp.{{entity}})

from uuid import UUID

from fastapi import APIRouter

from contracts.auth.v1 import auth_pb2 as pb
from gateway.dependencies import AuthCtx, Clients
from gateway.schemas.auth import UserOut
from gateway.schemas.common import ERRORS

router = APIRouter(prefix="/api/v1/users", tags=["users"], responses=ERRORS)


@router.get("/me")
async def me(ctx: AuthCtx, clients: Clients) -> UserOut:
    resp = await clients.auth.GetUser(pb.GetUserRequest(context=ctx))
    return UserOut.from_pb(resp.user)


@router.get("/{user_id}")
async def get_user(user_id: UUID, ctx: AuthCtx, clients: Clients) -> UserOut:
    resp = await clients.auth.GetUser(pb.GetUserRequest(context=ctx, user_id=str(user_id)))
    return UserOut.from_pb(resp.user)

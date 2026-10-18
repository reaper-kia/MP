from uuid import UUID

from auth.v1 import auth_service_pb2 as pb
from fastapi import APIRouter

from gateway.dependencies import AuthCtx, Clients
from gateway.schemas.auth import UserOut
from gateway.schemas.common import ERRORS

router = APIRouter(prefix="/api/v1/users", tags=["users"], responses=ERRORS)


@router.get("/me")
async def me(ctx: AuthCtx, clients: Clients) -> UserOut:
    result = await clients.auth.GetUser(pb.GetUserRequest(context=ctx))
    return UserOut.from_proto(result.user)


@router.get("/{user_id}")
async def get_user(user_id: UUID, ctx: AuthCtx, clients: Clients) -> UserOut:
    result = await clients.auth.GetUser(pb.GetUserRequest(context=ctx, user_id=str(user_id)))
    return UserOut.from_proto(result.user)

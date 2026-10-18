from datetime import datetime
from uuid import UUID

from auth.v1 import auth_service_pb2 as pb
from common.v1 import common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from auth_service.applications.context import RequestContext
from auth_service.applications.results.authentication import TokenPairResult
from auth_service.applications.results.read_models import UserReadModel

ROLE_TO_PROTO: dict[str, pb.UserRole] = {
    "user": pb.USER_ROLE_USER,
    "admin": pb.USER_ROLE_ADMIN,
}


def to_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def context_from_proto(ctx: common_pb2.RequestContext) -> RequestContext:
    return RequestContext(
        request_id=ctx.request_id,
        actor_user_id=UUID(ctx.actor_user_id) if ctx.actor_user_id else None,
        actor_role=ctx.actor_role or None,
    )


def user_to_proto(user: UserReadModel) -> pb.User:
    return pb.User(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=ROLE_TO_PROTO[user.role],
        created_at=to_timestamp(user.created_at),
    )


def tokens_to_proto(tokens: TokenPairResult) -> pb.TokenPair:
    return pb.TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_expires_at=to_timestamp(tokens.access_token_expire_at),
        refresh_expires_at=to_timestamp(tokens.refresh_token_expire_at),
    )

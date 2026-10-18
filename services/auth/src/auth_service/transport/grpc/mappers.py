from auth_service.application.dto import Tokens, UserView
from auth_service.domain.user import Role
from contracts.auth.v1 import auth_pb2 as pb
from platform_common.time import to_timestamp

ROLE_TO_PB = {Role.USER: pb.USER_ROLE_USER, Role.ADMIN: pb.USER_ROLE_ADMIN}


def user_to_pb(user: UserView) -> pb.User:
    return pb.User(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=ROLE_TO_PB[user.role],
        created_at=to_timestamp(user.created_at),
    )


def tokens_to_pb(tokens: Tokens) -> pb.TokenPair:
    return pb.TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_expires_at=to_timestamp(tokens.access_expires_at),
        refresh_expires_at=to_timestamp(tokens.refresh_expires_at),
    )

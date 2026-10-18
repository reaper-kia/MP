from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from contracts.auth.v1 import auth_pb2 as pb
from gateway.schemas.common import empty_to_none, ts

Role = Literal["user", "admin", "unknown"]
ROLE_FROM_PB: dict[int, Role] = {pb.USER_ROLE_USER: "user", pb.USER_ROLE_ADMIN: "admin"}


class RegisterIn(BaseModel):
    email: str = Field(max_length=254, examples=["alice@example.com"])
    name: str = Field(max_length=64, examples=["Alice"])
    password: str = Field(max_length=128, examples=["password123"])


class LoginIn(BaseModel):
    email: str = Field(max_length=254, examples=["alice@example.com"])
    password: str = Field(max_length=128, examples=["password123"])


class UserOut(BaseModel):
    id: UUID
    email: str | None
    name: str
    role: Role
    created_at: datetime

    @classmethod
    def from_pb(cls, user: pb.User) -> "UserOut":
        return cls(
            id=UUID(user.id),
            email=empty_to_none(user.email),
            name=user.name,
            role=ROLE_FROM_PB.get(user.role, "unknown"),
            created_at=ts(user.created_at),
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime

    @classmethod
    def from_pb(cls, tokens: pb.TokenPair) -> "TokenOut":
        return cls(access_token=tokens.access_token, access_expires_at=ts(tokens.access_expires_at))


class AuthOut(TokenOut):
    user: UserOut

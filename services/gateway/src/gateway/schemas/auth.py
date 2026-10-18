from datetime import datetime
from typing import Literal
from uuid import UUID

from auth.v1 import auth_service_pb2 as pb
from pydantic import BaseModel, Field

from gateway.schemas.common import ts

ROLE_FROM_PROTO: dict[int, str] = {pb.USER_ROLE_USER: "user", pb.USER_ROLE_ADMIN: "admin"}


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
    role: str
    created_at: datetime

    @classmethod
    def from_proto(cls, user: pb.User) -> "UserOut":
        return cls(
            id=UUID(user.id),
            email=user.email or None,
            name=user.name,
            role=ROLE_FROM_PROTO.get(user.role, "unknown"),
            created_at=ts(user.created_at),
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime


class AuthOut(TokenOut):
    user: UserOut

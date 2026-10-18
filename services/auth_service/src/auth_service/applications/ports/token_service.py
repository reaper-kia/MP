from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class IssuedAccessToken:
    value: str
    expires_at: datetime


class AccessTokenIssuer(Protocol):
    def issue(self, user_id: UUID, role: str, now: datetime) -> IssuedAccessToken: ...


class RefreshTokenService(Protocol):
    def generate(self) -> str: ...

    def hash(self, raw_token: str) -> str: ...

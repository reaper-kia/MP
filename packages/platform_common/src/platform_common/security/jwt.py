"""Access-токены (HS256). Auth выпускает, Gateway проверяет — секрет общий (JWT_SECRET)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from platform_common.errors import UnauthenticatedError
from platform_common.time import utcnow


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    role: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    expires_at: datetime


class InvalidTokenError(UnauthenticatedError):
    code = "INVALID_TOKEN"
    default_message = "Access token is invalid or expired"


class JwtCodec:
    algorithm = "HS256"

    def __init__(
        self,
        secret: str,
        *,
        issuer: str = "mp-auth",
        audience: str = "mp",
        ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        if not secret:
            raise ValueError("JWT secret must not be empty")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl

    def issue(self, user_id: UUID, role: str) -> IssuedToken:
        now = utcnow()
        expires_at = now + self._ttl
        payload = {
            "sub": str(user_id),
            "role": role,
            "iat": now,
            "exp": expires_at,
            "iss": self._issuer,
            "aud": self._audience,
            "jti": str(uuid4()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self.algorithm)
        return IssuedToken(token=token, expires_at=expires_at)

    def decode(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self.algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "exp", "role"]},
            )
            return AccessClaims(
                user_id=UUID(payload["sub"]),
                role=str(payload["role"]),
                expires_at=datetime.fromtimestamp(payload["exp"]).astimezone(),
            )
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise InvalidTokenError() from exc

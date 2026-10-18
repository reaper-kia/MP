from dataclasses import dataclass
from uuid import UUID

import jwt

from gateway.config import Settings
from gateway.errors import ApiError


@dataclass(frozen=True, slots=True)
class Actor:
    """Кто делает запрос — из проверенного access-токена."""

    user_id: UUID
    role: str


def decode_access_token(token: str, settings: Settings) -> Actor:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "role"]},
        )
        return Actor(user_id=UUID(payload["sub"]), role=str(payload["role"]))
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise ApiError(401, "INVALID_TOKEN", "Access token is invalid or expired") from e

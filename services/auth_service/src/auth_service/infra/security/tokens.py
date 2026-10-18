import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from auth_service.applications.ports.token_service import (
    AccessTokenIssuer,
    IssuedAccessToken,
    RefreshTokenService,
)


class JwtAccessTokenIssuer(AccessTokenIssuer):
    """HS256: тот же JWT_SECRET знает gateway и проверяет им токены."""

    def __init__(self, secret: str, issuer: str, audience: str, ttl: timedelta) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl

    def issue(self, user_id: UUID, role: str, now: datetime) -> IssuedAccessToken:
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
        return IssuedAccessToken(
            value=jwt.encode(payload, self._secret, algorithm="HS256"), expires_at=expires_at
        )


class SecureRefreshTokenService(RefreshTokenService):
    def generate(self) -> str:
        return secrets.token_urlsafe(48)

    def hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

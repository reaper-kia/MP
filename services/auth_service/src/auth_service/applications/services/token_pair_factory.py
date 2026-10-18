from dataclasses import dataclass
from datetime import datetime, timedelta

from auth_service.applications.ports.token_service import AccessTokenIssuer, RefreshTokenService
from auth_service.applications.results.authentication import TokenPairResult
from auth_service.domain.entities import RefreshSession, User


@dataclass(frozen=True)
class CreatedTokenPair:
    refresh_session: RefreshSession
    tokens: TokenPairResult


@dataclass
class TokenPairFactory:
    """Создаёт access-токен + refresh-сессию. Сохранить сессию — забота хэндлера."""

    access_tokens: AccessTokenIssuer
    refresh_tokens: RefreshTokenService
    refresh_token_ttl: timedelta

    def create(self, user: User, now: datetime) -> CreatedTokenPair:
        raw_refresh = self.refresh_tokens.generate()
        session = RefreshSession(
            user_id=user.id,
            token_hash=self.refresh_tokens.hash(raw_refresh),
            expires_at=now + self.refresh_token_ttl,
        )
        access = self.access_tokens.issue(user.id, user.role.value, now)
        return CreatedTokenPair(
            refresh_session=session,
            tokens=TokenPairResult(
                access_token=access.value,
                refresh_token=raw_refresh,
                access_token_expire_at=access.expires_at,
                refresh_token_expire_at=session.expires_at,
            ),
        )

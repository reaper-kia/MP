from datetime import timedelta

from auth_service.application.dto import Tokens
from auth_service.application.ports import AuthUnitOfWork, TokenService
from auth_service.domain.session import RefreshSession
from auth_service.domain.user import User


class SessionIssuer:
    """Выдаёт пару токенов и сохраняет refresh-сессию в текущем UoW."""

    def __init__(self, tokens: TokenService, refresh_ttl: timedelta) -> None:
        self._tokens = tokens
        self._refresh_ttl = refresh_ttl

    async def issue(self, uow: AuthUnitOfWork, user: User) -> Tokens:
        access = self._tokens.issue_access(user.id, user.role.value)
        refresh = self._tokens.new_refresh_token()
        session = RefreshSession.start(
            user.id, self._tokens.hash_refresh_token(refresh), self._refresh_ttl
        )
        await uow.sessions.add(session)
        return Tokens(
            access_token=access.token,
            access_expires_at=access.expires_at,
            refresh_token=refresh,
            refresh_expires_at=session.expires_at,
        )

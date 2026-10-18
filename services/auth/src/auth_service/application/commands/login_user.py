from dataclasses import dataclass

from auth_service.application.dto import AuthResult, UserView
from auth_service.application.ports import PasswordHasher, UnitOfWorkFactory
from auth_service.application.tokens import SessionIssuer
from auth_service.domain.errors import InvalidCredentialsError, InvalidEmailError
from auth_service.domain.user import normalize_email
from platform_common.context import RequestContext
from platform_common.mediator import Command


@dataclass(frozen=True, slots=True)
class LoginUser(Command[AuthResult]):
    ctx: RequestContext
    email: str
    password: str


class LoginUserHandler:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, issuer: SessionIssuer
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._issuer = issuer

    async def handle(self, cmd: LoginUser) -> AuthResult:
        try:
            email = normalize_email(cmd.email)
        except InvalidEmailError as exc:
            raise InvalidCredentialsError() from exc

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or not self._hasher.verify(user.password_hash, cmd.password):
                raise InvalidCredentialsError()
            tokens = await self._issuer.issue(uow, user)
            await uow.commit()

        return AuthResult(user=UserView.from_user(user), tokens=tokens)

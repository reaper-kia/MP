from dataclasses import dataclass

from auth_service.applications.commands.login_user import LoginUserCommand
from auth_service.applications.exceptions import InvalidCredentialsError
from auth_service.applications.ports.password_hasher import PasswordHasher
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory
from auth_service.applications.results.authentication import AuthenticationResult
from auth_service.applications.results.read_models import UserReadModel
from auth_service.applications.services.token_pair_factory import TokenPairFactory
from auth_service.domain.entities import utc_now
from auth_service.domain.exceptions import InvalidEmailError
from auth_service.domain.value_objects import Email


@dataclass
class LoginUserCommandHandler:
    uow_factory: UnitOfWorkFactory
    password_hasher: PasswordHasher
    token_pair_factory: TokenPairFactory

    async def handle(self, cmd: LoginUserCommand) -> AuthenticationResult:
        try:
            email = Email(cmd.email)
        except InvalidEmailError as exc:
            raise InvalidCredentialsError("Invalid email or password") from exc

        async with self.uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None:
                raise InvalidCredentialsError("Invalid email or password")

            if not await self.password_hasher.verify(cmd.password, user.password_hash):
                raise InvalidCredentialsError("Invalid email or password")

            created = self.token_pair_factory.create(user=user, now=utc_now())
            await uow.refresh_sessions.add(created.refresh_session)
            await uow.commit()

        return AuthenticationResult(user=UserReadModel.from_user(user), tokens=created.tokens)

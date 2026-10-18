from dataclasses import dataclass, field

from auth_service.applications.commands.register_user import RegisterUserCommand
from auth_service.applications.ports.password_hasher import PasswordHasher
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory
from auth_service.applications.results.authentication import AuthenticationResult
from auth_service.applications.results.read_models import UserReadModel
from auth_service.applications.services.token_pair_factory import TokenPairFactory
from auth_service.domain.entities import User, UserRole, utc_now
from auth_service.domain.exceptions import UserAlreadyRegisterError
from auth_service.domain.value_objects import Email, RawPassword, UserName


@dataclass
class RegisterUserCommandHandler:
    uow_factory: UnitOfWorkFactory
    password_hasher: PasswordHasher
    token_pair_factory: TokenPairFactory
    admin_emails: frozenset[str] = field(default_factory=frozenset)

    async def handle(self, cmd: RegisterUserCommand) -> AuthenticationResult:
        email = Email(cmd.email)
        name = UserName(cmd.name)
        raw_password = RawPassword(cmd.password)
        role = UserRole.ADMIN if email.value in self.admin_emails else UserRole.USER

        password_hash = await self.password_hasher.hash(raw_password.value)

        async with self.uow_factory() as uow:
            if await uow.users.get_by_email(email) is not None:
                raise UserAlreadyRegisterError("Email already registered")

            user = User.register(email=email, name=name, password_hash=password_hash, role=role)
            created = self.token_pair_factory.create(user=user, now=utc_now())

            await uow.users.add(user)
            await uow.refresh_sessions.add(created.refresh_session)
            await uow.commit()

        return AuthenticationResult(user=UserReadModel.from_user(user), tokens=created.tokens)

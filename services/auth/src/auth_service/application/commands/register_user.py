from dataclasses import dataclass

from auth_service.application.dto import AuthResult, UserView
from auth_service.application.ports import PasswordHasher, UnitOfWorkFactory
from auth_service.application.tokens import SessionIssuer
from auth_service.domain.errors import EmailTakenError
from auth_service.domain.user import Role, User, normalize_email, validate_password
from platform_common.context import RequestContext
from platform_common.mediator import Command

EVENTS_TOPIC = "auth.events"
USER_REGISTERED = "auth.user_registered.v1"


@dataclass(frozen=True, slots=True)
class RegisterUser(Command[AuthResult]):
    ctx: RequestContext
    email: str
    name: str
    password: str


class RegisterUserHandler:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        issuer: SessionIssuer,
        admin_emails: frozenset[str] = frozenset(),
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._issuer = issuer
        self._admin_emails = admin_emails

    async def handle(self, cmd: RegisterUser) -> AuthResult:
        email = normalize_email(cmd.email)
        validate_password(cmd.password)
        role = Role.ADMIN if email in self._admin_emails else Role.USER

        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(email) is not None:
                raise EmailTakenError()
            user = User.register(
                email=email, name=cmd.name, password_hash=self._hasher.hash(cmd.password), role=role
            )
            await uow.users.add(user)
            tokens = await self._issuer.issue(uow, user)
            uow.outbox.add(
                EVENTS_TOPIC,
                USER_REGISTERED,
                {"user_id": str(user.id), "email": user.email, "name": user.name},
                key=str(user.id),
            )
            await uow.commit()

        return AuthResult(user=UserView.from_user(user), tokens=tokens)

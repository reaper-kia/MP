from dataclasses import dataclass

from auth_service.applications.context import RequestContext
from auth_service.applications.mediator import Command
from auth_service.applications.results.authentication import AuthenticationResult


@dataclass(frozen=True)
class RegisterUserCommand(Command[AuthenticationResult]):
    ctx: RequestContext
    email: str
    name: str
    password: str

from dataclasses import dataclass

from auth_service.applications.context import RequestContext
from auth_service.applications.mediator import Command


@dataclass(frozen=True)
class LogoutUserCommand(Command[None]):
    ctx: RequestContext
    refresh_token: str

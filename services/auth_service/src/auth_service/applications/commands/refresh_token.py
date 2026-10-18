from dataclasses import dataclass

from auth_service.applications.context import RequestContext
from auth_service.applications.mediator import Command
from auth_service.applications.results.authentication import TokenPairResult


@dataclass(frozen=True)
class RefreshTokenCommand(Command[TokenPairResult]):
    ctx: RequestContext
    refresh_token: str

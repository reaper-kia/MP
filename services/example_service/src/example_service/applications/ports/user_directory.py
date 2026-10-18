from typing import Protocol
from uuid import UUID

from example_service.applications.context import RequestContext


class UserDirectory(Protocol):
    """Пользователи живут в auth_service — получаем их по gRPC (infra/clients/auth_client.py)."""

    async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None: ...

import pytest

from auth_service.applications.mediator import Mediator
from auth_service.dependencies import AuthDeps, build_mediator
from auth_service.infra.config import Settings
from tests.fakes import (
    FakeAccessTokenIssuer,
    FakeDb,
    FakePasswordHasher,
    FakeRefreshTokenService,
    FakeUnitOfWork,
)


@pytest.fixture
def db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def mediator(db: FakeDb) -> Mediator:
    deps = AuthDeps(
        uow_factory=lambda: FakeUnitOfWork(db),
        password_hasher=FakePasswordHasher(),
        access_tokens=FakeAccessTokenIssuer(),
        refresh_tokens=FakeRefreshTokenService(),
    )
    return build_mediator(Settings(admin_emails="boss@example.com"), deps)

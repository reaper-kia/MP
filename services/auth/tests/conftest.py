import pytest

from auth_service.config import Settings
from auth_service.container import build_mediator
from platform_common.mediator import Mediator
from tests.fakes import FakeDb, FakeHasher, FakeTokens, FakeUnitOfWork


@pytest.fixture
def db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def mediator(db: FakeDb) -> Mediator:
    settings = Settings(admin_emails="boss@example.com")
    return build_mediator(settings, lambda: FakeUnitOfWork(db), FakeHasher(), FakeTokens())

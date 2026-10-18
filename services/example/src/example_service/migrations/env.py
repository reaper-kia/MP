from example_service.infra.db.models import Base
from platform_common.db.alembic_env import run_alembic

run_alembic(Base.metadata)

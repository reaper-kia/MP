from platform_common.db.alembic_env import run_alembic

from {{name}}_service.infra.db.models import Base

run_alembic(Base.metadata)

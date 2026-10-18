import logging

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(url, echo=echo, pool_pre_ping=True, pool_size=10, max_overflow=10)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def ensure_database(url: str) -> None:
    """CREATE DATABASE, если её ещё нет. Поэтому новому сервису не нужно править
    init-скрипты Postgres — достаточно указать database_name в его Settings."""
    sa_url = make_url(url)
    db_name = sa_url.database
    if not db_name:
        raise ValueError("Database name is missing in URL")
    conn = await asyncpg.connect(
        host=sa_url.host,
        port=sa_url.port or 5432,
        user=sa_url.username,
        password=sa_url.password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            # имя БД берём из своих же настроек, не из пользовательского ввода
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info("Created database %s", db_name)
    except asyncpg.DuplicateDatabaseError:
        pass  # параллельный старт двух реплик
    finally:
        await conn.close()

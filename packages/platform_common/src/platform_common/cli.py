"""Единый CLI для всех сервисов:

<service> run                     # migrate + serve (так стартует контейнер)
<service> serve                   # только gRPC-сервер
<service> migrate                 # создать БД (если нет) + alembic upgrade head
<service> makemigrations "msg"    # alembic revision --autogenerate
"""

import argparse
import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from platform_common.config import BaseServiceSettings
from platform_common.db.engine import ensure_database
from platform_common.db.migrations import make_revision, upgrade_head
from platform_common.logging import setup_logging


def service_cli[S: BaseServiceSettings](
    *,
    settings_factory: Callable[[], S],
    serve: Callable[[S], Coroutine[Any, Any, None]],
    migrations_dir: Path | None,
) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="migrate + serve (default)")
    sub.add_parser("serve", help="start gRPC server only")
    sub.add_parser("migrate", help="create database if missing and apply migrations")
    mk = sub.add_parser("makemigrations", help="autogenerate a new alembic revision")
    mk.add_argument("message")
    args = parser.parse_args()
    command = args.command or "run"

    settings = settings_factory()
    setup_logging(settings.log_level, settings.service_name)

    def migrate() -> None:
        if migrations_dir is None:
            return
        asyncio.run(ensure_database(settings.database_url))
        upgrade_head(migrations_dir, settings.database_url)

    if command in ("run", "migrate"):
        migrate()
    if command == "makemigrations":
        if migrations_dir is None:
            raise SystemExit("This service has no database")
        asyncio.run(ensure_database(settings.database_url))
        upgrade_head(migrations_dir, settings.database_url)
        make_revision(migrations_dir, settings.database_url, args.message)
    if command in ("run", "serve"):
        asyncio.run(serve(settings))

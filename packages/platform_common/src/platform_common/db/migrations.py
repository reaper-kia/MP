"""Alembic без alembic.ini: миграции лежат внутри пакета сервиса (<pkg>/migrations).

CLI сервиса (`<service> migrate`, `<service> makemigrations "msg"`) вызывает эти функции.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config(migrations_dir: Path, database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    cfg.set_main_option("file_template", "%%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s")
    return cfg


def upgrade_head(migrations_dir: Path, database_url: str) -> None:
    command.upgrade(alembic_config(migrations_dir, database_url), "head")


def make_revision(migrations_dir: Path, database_url: str, message: str) -> None:
    command.revision(
        alembic_config(migrations_dir, database_url), message=message, autogenerate=True
    )

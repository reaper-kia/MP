"""Таблицы search_db. Задача B2-01: схема — ARCHITECTURE §4, типы колонок — B2-01 в
docs/tasks/B2-search.md. После добавления моделей:
    make db && make migration s=search_service m="init"

Модуль импортируется в migrations/env.py, чтобы таблицы попали в Base.metadata.
"""

from search_service.infra.database.base import Base

__all__ = ["Base"]

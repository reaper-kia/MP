"""Каркас: все сценарии зарегистрированы, период считается по Красноярску."""

import inspect
from datetime import UTC, date, datetime

import pytest

from search_service.applications import commands, queries
from search_service.applications.commands import results as c_results
from search_service.applications.commands import searches as c_searches
from search_service.applications.commands import sources as c_sources
from search_service.applications.mediator import Command
from search_service.applications.queries import results as q_results
from search_service.applications.queries import searches as q_searches
from search_service.applications.queries import sources as q_sources
from search_service.dependencies import build_mediator
from search_service.domain.exceptions import InvalidPeriodError
from search_service.domain.value_objects import UtcPeriod
from tests.fakes import FakeCollector, FakeRunner, InMemoryUoW

MODULES = [c_sources, c_searches, c_results, q_sources, q_searches, q_results]


def command_types() -> list[type]:
    found = []
    for module in MODULES:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Command)
                and obj is not Command
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return found


def test_every_command_has_handler() -> None:
    assert commands and queries  # пакеты на месте
    mediator = build_mediator(InMemoryUoW(), FakeCollector(), FakeRunner())
    registered = set(mediator._handlers)  # проверяем проводку
    missing = [t.__name__ for t in command_types() if t not in registered]
    assert not missing, f"нет хэндлера для: {missing}"
    assert len(command_types()) == 15  # по одному на RPC search.v1


def test_period_krasnoyarsk_bounds() -> None:
    period = UtcPeriod.from_local_dates(date(2026, 10, 1), date(2026, 10, 19))
    assert period.start == datetime(2026, 9, 30, 17, 0, tzinfo=UTC)
    assert period.end == datetime(2026, 10, 19, 16, 59, 59, 999999, tzinfo=UTC)
    assert period.contains(period.start) and period.contains(period.end)


def test_period_validation() -> None:
    with pytest.raises(InvalidPeriodError, match="period_from"):
        UtcPeriod.from_local_dates(date(2026, 10, 2), date(2026, 10, 1))
    with pytest.raises(InvalidPeriodError):
        UtcPeriod.from_local_dates(date(2025, 1, 1), date(2026, 10, 1))

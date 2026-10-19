"""Слои зависят только вниз: domain ← applications ← infra / transport (как в search_service).

Если тест упал — в слой попал импорт «снизу вверх»; вынеси зависимость в порт
(applications/ports/) и подставь реализацию в dependencies.py.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "collector_service"

# слой → какие слои ему импортировать нельзя
FORBIDDEN: dict[str, set[str]] = {
    "domain": {"applications", "infra", "transport", "dependencies"},
    "applications": {"infra", "transport", "dependencies"},
    "infra": {"transport", "dependencies"},
}


def imported_layers(path: Path) -> set[str]:
    layers: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        layers.update(n.split(".")[1] for n in names if n.startswith("collector_service."))
    return layers


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_does_not_import_upwards(layer: str) -> None:
    files = sorted((SRC / layer).rglob("*.py"))
    assert files, f"в {layer}/ нет файлов — проверка ничего не проверяет"
    for path in files:
        bad = imported_layers(path) & FORBIDDEN[layer]
        assert not bad, f"{path.relative_to(SRC)} импортирует {sorted(bad)}"

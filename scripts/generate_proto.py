"""Генерация Python-кода из contracts/**/*.proto в packages/platform_contracts/src.

Запуск: make proto
"""

import re
from pathlib import Path

import grpc_tools
from grpc_tools import protoc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
PACKAGE_DIR = PROJECT_ROOT / "packages" / "platform_contracts"
OUTPUT_DIR = PACKAGE_DIR / "src"


def main() -> None:
    if grpc_tools.__file__ is None:
        raise RuntimeError("Cannot locate grpc_tools installation")

    well_known_types_dir = Path(grpc_tools.__file__).resolve().parent / "_proto"
    proto_files = sorted(CONTRACTS_DIR.rglob("*.proto"))
    if not proto_files:
        raise RuntimeError(f"No .proto files found in {CONTRACTS_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Старые сгенерированные файлы удаляем, чтобы удалённый .proto не оставил мусор
    for old in OUTPUT_DIR.rglob("*_pb2*.py*"):
        old.unlink()

    arguments = [
        "grpc_tools.protoc",
        f"--proto_path={CONTRACTS_DIR}",
        f"--proto_path={well_known_types_dir}",
        f"--python_out={OUTPUT_DIR}",
        f"--pyi_out={OUTPUT_DIR}",
        f"--grpc_python_out={OUTPUT_DIR}",
        *(str(path.relative_to(CONTRACTS_DIR)) for path in proto_files),
    ]
    exit_code = protoc.main(arguments)
    if exit_code != 0:
        raise SystemExit(exit_code)

    # __init__.py + py.typed в каждом пакете (search/, search/v1/, ...)
    top_level = sorted({p.relative_to(CONTRACTS_DIR).parts[0] for p in proto_files})
    for name in top_level:
        for directory in [OUTPUT_DIR / name, *(OUTPUT_DIR / name).rglob("*")]:
            if directory.is_dir() and directory.name != "__pycache__":
                (directory / "__init__.py").touch()
        (OUTPUT_DIR / name / "py.typed").touch()

    # module-name в pyproject.toml пакета = список верхних пакетов
    pyproject = PACKAGE_DIR / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    modules = ", ".join(f'"{name}"' for name in top_level)
    text = re.sub(r"module-name = \[.*?\]", f"module-name = [{modules}]", text)
    pyproject.write_text(text, encoding="utf-8")

    print(f"Generated {len(proto_files)} proto files into {OUTPUT_DIR}: {', '.join(top_level)}")


if __name__ == "__main__":
    main()

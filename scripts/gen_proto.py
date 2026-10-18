"""Генерация Python-кода из contracts/**/*.proto в packages/contracts/src/contracts.

Запуск: `make proto` (или `uv run python scripts/gen_proto.py`).
Сгенерированный код коммитится: Docker-сборке и CI не нужен protoc.
"""

from pathlib import Path

import grpc_tools
from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]
PROTO_ROOT = ROOT  # proto-пакет contracts.x.v1 лежит в ./contracts/x/v1
CONTRACTS_DIR = ROOT / "contracts"
OUT_DIR = ROOT / "packages" / "contracts" / "src"
GENERATED_SUFFIXES = ("_pb2.py", "_pb2.pyi", "_pb2_grpc.py")


def clean_generated(package_dir: Path) -> None:
    for path in package_dir.rglob("*"):
        if path.is_file() and path.name.endswith(GENERATED_SUFFIXES):
            path.unlink()


def ensure_init_files(package_dir: Path) -> None:
    for directory in [package_dir, *(p for p in package_dir.rglob("*") if p.is_dir())]:
        if directory.name == "__pycache__":
            continue
        (directory / "__init__.py").touch()
    (package_dir / "py.typed").touch()


def main() -> None:
    if grpc_tools.__file__ is None:
        raise RuntimeError("grpc_tools not found: run `uv sync --all-packages`")
    well_known = Path(grpc_tools.__file__).resolve().parent / "_proto"

    protos = sorted(CONTRACTS_DIR.rglob("*.proto"))
    if not protos:
        raise SystemExit(f"No .proto files in {CONTRACTS_DIR}")

    package_dir = OUT_DIR / "contracts"
    package_dir.mkdir(parents=True, exist_ok=True)
    clean_generated(package_dir)

    args = [
        "grpc_tools.protoc",
        f"--proto_path={PROTO_ROOT}",
        f"--proto_path={well_known}",
        f"--python_out={OUT_DIR}",
        f"--pyi_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        *(str(p.relative_to(PROTO_ROOT)) for p in protos),
    ]
    code = protoc.main(args)
    if code != 0:
        raise SystemExit(code)

    ensure_init_files(package_dir)
    for proto in protos:
        print(f"  {proto.relative_to(ROOT)}")
    print(f"Generated {len(protos)} proto file(s) -> {package_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

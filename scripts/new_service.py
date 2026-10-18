"""Каркас нового gRPC-сервиса за одну команду.

    make new-service name=orders                       # сущность Order, порт — следующий свободный
    make new-service name=orders entity=Order port=50060
    uv run python scripts/new_service.py booking --entity Booking --plural Bookings

Создаёт:
  contracts/<name>/v1/<name>.proto              — контракт (правь его первым!)
  services/<name>/                              — сервис: domain / application / infra / transport
  services/gateway/src/gateway/routers/<name>.py + schemas/<name>.py  — HTTP-ручки
и прописывает сервис в compose.yaml, gateway (config, clients, main) и mypy_path.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "service"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
ENTITY_RE = re.compile(r"^[A-Z][A-Za-z0-9]{1,40}$")
RESERVED = {"gateway", "common", "contracts", "platform_common", "frontend"}


def pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def snake(pascal_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", pascal_name).lower()


def default_entity(name: str) -> str:
    base = pascal(name)
    return base[:-1] if base.endswith("s") and len(base) > 3 else base


def next_port() -> int:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    ports = [int(p) for p in re.findall(r'"127\.0\.0\.1:(50\d{3}):50\d{3}"', compose)]
    return max(ports, default=50050) + 1


def render(text: str, tokens: dict[str, str]) -> str:
    for key, value in tokens.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def insert_before(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        raise SystemExit(f"Marker '{marker}' not found in {path.relative_to(ROOT)}")
    line_start = text.rfind("\n", 0, text.index(marker)) + 1
    path.write_text(text[:line_start] + block + text[line_start:], encoding="utf-8")


def copy_tree(src_root: Path, dst_root: Path, tokens: dict[str, str]) -> list[Path]:
    created: list[Path] = []
    for src in sorted(src_root.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = Path(render(str(src.relative_to(src_root)), tokens))
        dst = dst_root / rel
        if dst.exists():
            raise SystemExit(f"Already exists: {dst.relative_to(ROOT)}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(render(src.read_text(encoding="utf-8"), tokens), encoding="utf-8")
        created.append(dst)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("name", help="snake_case имя сервиса: orders, booking, notifications")
    parser.add_argument("--entity", help="главная сущность в PascalCase (по умолчанию из name)")
    parser.add_argument("--plural", help="множественное число сущности (по умолчанию +s)")
    parser.add_argument("--port", type=int, help="gRPC-порт (по умолчанию следующий свободный)")
    args = parser.parse_args()

    name: str = args.name
    if not NAME_RE.match(name) or name in RESERVED:
        raise SystemExit(f"Bad service name: {name!r} (snake_case, not one of {sorted(RESERVED)})")
    if (ROOT / "services" / name).exists():
        raise SystemExit(f"services/{name} already exists")

    entity: str = args.entity or default_entity(name)
    if not ENTITY_RE.match(entity):
        raise SystemExit(f"Bad entity name: {entity!r} (PascalCase)")
    entities: str = args.plural or f"{entity}s"
    port: int = args.port or next_port()

    tokens = {
        "name": name,
        "Name": pascal(name),
        "NAME": name.upper(),
        "project": f"{name.replace('_', '-')}-service",
        "url": name.replace("_", "-"),
        "port": str(port),
        "Entity": entity,
        "entity": snake(entity),
        "ENTITY": snake(entity).upper(),
        "Entities": entities,
        "entities": snake(entities),
    }

    created: list[Path] = []
    created += copy_tree(TEMPLATE / "contracts", ROOT / "contracts", tokens)
    created += copy_tree(TEMPLATE / "services", ROOT / "services", tokens)
    created += copy_tree(
        TEMPLATE / "gateway", ROOT / "services" / "gateway" / "src" / "gateway", tokens
    )

    # ── регистрация в compose / gateway / mypy ──
    compose = ROOT / "compose.yaml"
    insert_before(
        compose,
        "# >>> services",
        render(
            """  {{name}}:
    build:
      <<: *python-build
      args:
        PACKAGE: {{project}}
    command: ["{{project}}", "run"]
    restart: unless-stopped
    environment:
      <<: *service-env
    ports:
      - "127.0.0.1:{{port}}:{{port}}"
    depends_on: *service-depends
    healthcheck:
      test: ["CMD", "python", "-m", "platform_common.grpc.healthcheck", "localhost:{{port}}"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 15s

""",
            tokens,
        ),
    )
    insert_before(
        compose, "# >>> gateway grpc targets", f"      {name.upper()}_GRPC_TARGET: {name}:{port}\n"
    )

    gw = ROOT / "services" / "gateway" / "src" / "gateway"
    insert_before(
        gw / "config.py",
        "# >>> grpc targets",
        f'    {name}_grpc_target: str = "localhost:{port}"\n',
    )
    insert_before(
        gw / "clients.py",
        "# >>> grpc imports",
        f"from contracts.{name}.v1 import {name}_pb2_grpc\n",
    )
    insert_before(
        gw / "clients.py",
        "# >>> grpc clients",
        render(
            "        self.{{name}}: Any = {{name}}_pb2_grpc.{{Name}}ServiceStub(\n"
            '            self._channel("{{name}}", settings.{{name}}_grpc_target)\n'
            "        )\n",
            tokens,
        ),
    )
    insert_before(
        gw / "main.py",
        "# >>> router imports",
        f"from gateway.routers import {name} as {name}_router\n",
    )
    insert_before(
        gw / "main.py", "# >>> routers", f"    app.include_router({name}_router.router)\n"
    )
    insert_before(ROOT / "pyproject.toml", "# >>> mypy_path", f'    "services/{name}/src",\n')

    print(f"Created service '{name}' (entity {entity}, gRPC port {port}):")
    for path in created:
        print(f"  + {path.relative_to(ROOT)}")
    print("  ~ compose.yaml, gateway config/clients/main, pyproject.toml (mypy_path)")

    # ── генерация кода из proto и автоформат (best effort) ──
    run([sys.executable, str(ROOT / "scripts" / "gen_proto.py")])
    if shutil.which("ruff") or shutil.which("uv"):
        paths = [str(ROOT / "services" / name), str(gw)]
        ruff = ["ruff"] if shutil.which("ruff") else ["uv", "run", "ruff"]
        run([*ruff, "format", "-q", *paths], check=False)
        run([*ruff, "check", "--fix", "-q", *paths], check=False)
        run([*ruff, "format", "-q", *paths], check=False)

    print(
        f"""
Дальше:
  1. contracts/{name}/v1/{name}.proto  — опиши RPC и сообщения → make proto
  2. services/{name}/src/{name}_service — domain → application (команды/запросы) → infra → servicer
  3. модели поменял → make migration s={name} m="describe change"
  4. uv sync --all-packages && make up   (или make run s={name})
  5. ручки: services/gateway/src/gateway/routers/{name}.py → http://localhost:8000/docs
"""
    )


def run(cmd: list[str], check: bool = True) -> None:
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

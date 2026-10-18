"""Новый сервис = копия example_service с переименованием.

    make new-service name=orders                    # services/orders_service, сущность остаётся Item
    make new-service name=orders entity=Order       # + Item → Order, items → orders
    make new-service name=orders entity=Order port=50053 db_port=5435

Что делает:
  1. копирует contracts/example → contracts/<name> и services/example_service → services/<name>_service
  2. заменяет имена в коде, путях, портах, БД
  3. печатает, что дописать руками в compose.yaml, gateway и CI
Ничего за пределами новых папок скрипт не меняет.
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".env", "uv.lock"}


def pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def used_ports(pattern: str) -> list[int]:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    return [int(p) for p in re.findall(pattern, compose)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="snake_case: orders, booking, notifications")
    parser.add_argument("--entity", help="переименовать Item в эту сущность (PascalCase): Order")
    parser.add_argument("--port", type=int, help="gRPC-порт (по умолчанию следующий свободный)")
    parser.add_argument("--db-port", type=int, help="порт БД на хосте (по умолчанию следующий)")
    args = parser.parse_args()

    name: str = args.name
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in {"example", "auth", "common", "gateway"}:
        raise SystemExit(f"Bad name: {name!r}")
    target = ROOT / "services" / f"{name}_service"
    if target.exists():
        raise SystemExit(f"{target.relative_to(ROOT)} already exists")

    port = args.port or max(used_ports(r'"127\.0\.0\.1:(50\d{3}):50\d{3}"'), default=50050) + 1
    db_port = args.db_port or max(used_ports(r'"127\.0\.0\.1:(54\d{2}):5432"'), default=5432) + 1
    Name = pascal(name)

    # порядок важен: сначала длинные строки
    replacements: list[tuple[str, str]] = [
        ("example_service", f"{name}_service"),
        ("example-service", f"{name.replace('_', '-')}-service"),
        ("ExampleService", f"{Name}Service"),
        ("Example gRPC", f"{Name} gRPC"),
        ("example.v1", f"{name}.v1"),
        ("example:example_local@localhost:5434/example", f"{name}:{name}_local@localhost:{db_port}/{name}"),
        ("50052", str(port)),
        ('"common", "example"]', f'"common", "{name}"]'),
        ('"common.*", "example.*"]', f'"common.*", "{name}.*"]'),
        ("contracts/example/", f"contracts/{name}/"),
        ("package example.v1;", f"package {name}.v1;"),
    ]
    if args.entity:
        entity = args.entity
        plural = entity + "s"
        replacements += [
            ("items", snake(plural)),
            ("Items", plural),
            ("ITEM", snake(entity).upper()),
            ("Item", entity),
            ("item", snake(entity)),
        ]

    def render(text: str) -> str:
        text = text.replace(".items()", "\0DICT_PAIRS\0")  # dict.items() не переименовываем
        for old, new in replacements:
            text = text.replace(old, new)
        return text.replace("\0DICT_PAIRS\0", ".items()")

    def copy_tree(src: Path, dst: Path) -> None:
        for path in sorted(src.rglob("*")):
            if any(part in SKIP for part in path.parts) or path.is_dir():
                continue
            rel = Path(render(str(path.relative_to(src))))
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(path.read_text(encoding="utf-8")), encoding="utf-8")

    copy_tree(ROOT / "contracts" / "example", ROOT / "contracts" / name)
    copy_tree(ROOT / "services" / "example_service", target)

    # после переименований могли поехать сортировка импортов и длина строк
    ruff = shutil.which("ruff")
    if ruff:
        for args_ in (["format", "-q"], ["check", "--fix", "-q"], ["format", "-q"]):
            subprocess.run([ruff, *args_, str(target)], check=False)

    entity_note = f", Item → {args.entity}" if args.entity else ""
    print(
        f"""
Создано: contracts/{name}/, services/{name}_service/ (gRPC :{port}, БД :{db_port}{entity_note})

Осталось руками (2–3 минуты):

1) compose.yaml — добавь два блока (рядом с example_service):

  {name}_service:
    build:
      context: .
      dockerfile: services/{name}_service/Dockerfile
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://{name}:${{{name.upper()}_DB_PASSWORD:-{name}_local}}@{name}_db:5432/{name}
      AUTH_GRPC_TARGET: auth_service:50051
    ports:
      - "127.0.0.1:{port}:{port}"
    depends_on:
      {name}_db:
        condition: service_healthy

  {name}_db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: {name}
      POSTGRES_USER: {name}
      POSTGRES_PASSWORD: ${{{name.upper()}_DB_PASSWORD:-{name}_local}}
    ports:
      - "127.0.0.1:{db_port}:5432"
    volumes:
      - {name}_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {name} -d {name}"]
      interval: 5s
      timeout: 3s
      retries: 10

   + в volumes: внизу:   {name}_db_data:
   + у gateway в environment:   {name.upper()}_GRPC_TARGET: {name}_service:{port}
   + у gateway в depends_on:    - {name}_service

2) gateway:
   config.py        {name}_grpc_target: str = "localhost:{port}"
   grpc_clients.py  from {name}.v1 import {name}_service_pb2_grpc
                    self.{name}: Any = {name}_service_pb2_grpc.{Name}ServiceStub(
                        self._channel("{name}", settings.{name}_grpc_target)
                    )
   routers/         скопируй routers/items.py → routers/{name}.py, поправь вызовы,
                    подключи в main.py: app.include_router({name}.router)

3) .github/workflows/ci.yml — добавь {name}_service в matrix.service
   infra/ansible/roles/env/templates/env.j2 — строка {name.upper()}_DB_PASSWORD по образцу EXAMPLE_DB_PASSWORD
   .env.example — {name.upper()}_DB_PASSWORD={name}_local

4) make proto && make install && make fmt && make up
"""
    )


if __name__ == "__main__":
    main()

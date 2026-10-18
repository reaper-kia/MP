from pathlib import Path

from contracts.{{name}}.v1 import {{name}}_pb2, {{name}}_pb2_grpc
from platform_common.cli import service_cli
from platform_common.grpc.server import bind, run_grpc_server

from {{name}}_service.config import Settings, get_settings
from {{name}}_service.container import build_container
from {{name}}_service.transport.grpc.servicer import {{Name}}Servicer

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def serve(settings: Settings) -> None:
    container = build_container(settings)
    await run_grpc_server(
        address=settings.grpc_address,
        bindings=[
            bind(
                {{name}}_pb2_grpc.add_{{Name}}ServiceServicer_to_server,
                {{Name}}Servicer(container.mediator),
                {{name}}_pb2,
                "{{Name}}Service",
            )
        ],
        background=container.background,
        on_shutdown=container.close,
    )


def main() -> None:
    service_cli(settings_factory=get_settings, serve=serve, migrations_dir=MIGRATIONS_DIR)


if __name__ == "__main__":
    main()

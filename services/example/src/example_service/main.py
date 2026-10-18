from pathlib import Path

from contracts.example.v1 import example_pb2, example_pb2_grpc
from example_service.config import Settings, get_settings
from example_service.container import build_container
from example_service.transport.grpc.servicer import ExampleServicer
from platform_common.cli import service_cli
from platform_common.grpc.server import bind, run_grpc_server

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def serve(settings: Settings) -> None:
    container = build_container(settings)
    await run_grpc_server(
        address=settings.grpc_address,
        bindings=[
            bind(
                example_pb2_grpc.add_ExampleServiceServicer_to_server,
                ExampleServicer(container.mediator),
                example_pb2,
                "ExampleService",
            )
        ],
        background=container.background,
        on_shutdown=container.close,
    )


def main() -> None:
    service_cli(settings_factory=get_settings, serve=serve, migrations_dir=MIGRATIONS_DIR)


if __name__ == "__main__":
    main()

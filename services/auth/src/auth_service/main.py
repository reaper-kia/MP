from pathlib import Path

from auth_service.config import Settings, get_settings
from auth_service.container import build_container
from auth_service.transport.grpc.servicer import AuthServicer
from contracts.auth.v1 import auth_pb2, auth_pb2_grpc
from platform_common.cli import service_cli
from platform_common.grpc.server import bind, run_grpc_server

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def serve(settings: Settings) -> None:
    container = build_container(settings)
    await run_grpc_server(
        address=settings.grpc_address,
        bindings=[
            bind(
                auth_pb2_grpc.add_AuthServiceServicer_to_server,
                AuthServicer(container.mediator),
                auth_pb2,
                "AuthService",
            )
        ],
        background=container.background,
        on_shutdown=container.close,
    )


def main() -> None:
    service_cli(settings_factory=get_settings, serve=serve, migrations_dir=MIGRATIONS_DIR)


if __name__ == "__main__":
    main()

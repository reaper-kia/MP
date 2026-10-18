"""Docker healthcheck: python -m platform_common.grpc.healthcheck localhost:50051"""

import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "localhost:50051"
    try:
        with grpc.insecure_channel(target) as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            resp = stub.Check(health_pb2.HealthCheckRequest(), timeout=2)  # type: ignore[attr-defined]
            return 0 if resp.status == health_pb2.HealthCheckResponse.SERVING else 1
    except grpc.RpcError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

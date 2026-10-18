from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_timestamp(value: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(value)
    return ts


def from_timestamp(ts: Timestamp) -> datetime:
    return ts.ToDatetime(tzinfo=UTC)

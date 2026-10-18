import uuid
from datetime import datetime

from platform_common.db.base import make_metadata
from platform_common.kafka.outbox import OutboxMixin
from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = make_metadata()


class {{Entity}}Model(Base):
    __tablename__ = "{{entities}}"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxMessage(OutboxMixin, Base):
    """События этого сервиса: uow.outbox.add(topic, type, payload). См. docs/events.md"""

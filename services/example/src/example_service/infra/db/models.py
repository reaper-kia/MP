import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from platform_common.db.base import make_metadata
from platform_common.kafka.outbox import OutboxMixin, ProcessedEventMixin


class Base(DeclarativeBase):
    metadata = make_metadata()


class ItemModel(Base):
    __tablename__ = "items"
    __table_args__ = (Index("ix_items_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxMessage(OutboxMixin, Base):
    pass


class ProcessedEvent(ProcessedEventMixin, Base):
    pass

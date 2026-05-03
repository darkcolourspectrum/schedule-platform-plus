"""
Таблица обработанных событий - для идемпотентности consumer'а.

Outbox-паттерн даёт гарантии at-least-once: одно событие может быть
доставлено несколько раз (например, если воркер упал между publish
и UPDATE published_at). Чтобы не создавать дубликаты уведомлений,
перед обработкой проверяем, не было ли это event_id уже обработано.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedEvent(Base):
    """Событие, успешно обработанное consumer'ом."""
    
    __tablename__ = "processed_events"
    
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    def __repr__(self) -> str:
        return f"<ProcessedEvent(event_id={self.event_id}, type={self.event_type})>"
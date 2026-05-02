"""
Таблица идемпотентности для consumer'ов событий.

При at-least-once-доставке RabbitMQ одно и то же событие может прийти
несколько раз. Перед обработкой consumer проверяет event_id в этой таблице,
и записывает после успешной обработки.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedEvent(Base):
    """Запись об уже обработанном событии для идемпотентности."""
    
    __tablename__ = "processed_events"
    
    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    def __repr__(self) -> str:
        return f"<ProcessedEvent(event_id={self.event_id}, type={self.event_type})>"
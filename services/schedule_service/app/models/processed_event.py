"""
Таблица идемпотентности для consumer'ов событий.

При at-least-once-доставке RabbitMQ одно и то же событие может прийти
несколько раз (если consumer упал после обработки, но до ack;
если publisher переотправил при сбое сети). Чтобы дважды не применять
изменения, consumer перед обработкой проверяет: не видели ли мы уже
event_id, и записывает его после успешной обработки.

Retention: записи живут условно вечно (пока не зачистим cleanup-воркером).
В будущем добавим TTL ~7-30 дней - дольше окно дубликатов в RabbitMQ
не бывает, а накапливать миллионы строк бессмысленно.
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
    
    # event_id из payload события - первичный ключ.
    # Если попытка вставить дубликат - сработает PK constraint, consumer
    # это поймает и пропустит обработку.
    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    
    # Тип события для отладки и метрик ('user.created', 'user.updated', ...).
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Когда мы обработали это событие.
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    def __repr__(self) -> str:
        return f"<ProcessedEvent(event_id={self.event_id}, type={self.event_type})>"
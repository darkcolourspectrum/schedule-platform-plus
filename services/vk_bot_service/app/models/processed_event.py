"""ProcessedEvent model - идемпотентность RabbitMQ-consumer'ов."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedEvent(Base):
    """
    Журнал обработанных событий для дедупликации.

    Consumer'ы (schedule_events, auth_events) при at-least-once доставке
    могут получить одно событие несколько раз. Перед обработкой проверяем
    наличие event_id здесь; после обработки записываем его в той же
    транзакции, что и бизнес-изменения. Повторная доставка пропускается.
    """

    __tablename__ = "processed_events"

    # event_id - первичный ключ. Совпадает с event_id из payload события.
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )

    # Тип события (lesson.created, user.updated и т.п.) - для аудита.
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

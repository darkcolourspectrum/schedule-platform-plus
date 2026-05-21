"""
Модель ProcessedEvent - журнал обработанных событий для идемпотентности.

CRM подписан на чужие события (auth_events) через consumer. Доставка
RabbitMQ - at-least-once: одно и то же событие может прийти повторно
(ретрай publisher'а, переотправка после краха consumer'а).

Перед обработкой события handler проверяет, нет ли его event_id в этой
таблице. Если есть - событие уже применено, повторная обработка
пропускается. После успешной обработки event_id записывается сюда -
в той же транзакции, что и само изменение данных.

Это стандартный паттерн дедупликации, единый для всех сервисов проекта.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedEvent(Base):
    """Запись об уже обработанном событии (для идемпотентности consumer'а)."""

    __tablename__ = "processed_events"

    # event_id события выступает первичным ключом: повторная вставка того
    # же id вызовет нарушение PK - это и есть защита от дублей на уровне БД.
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )

    # Тип события - для логирования и разбора инцидентов.
    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    # Когда событие было обработано этим сервисом.
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedEvent(event_id={self.event_id}, "
            f"event_type={self.event_type})>"
        )
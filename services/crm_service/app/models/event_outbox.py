"""
Outbox для надёжной публикации событий из CRM Service.

Зачем нужен:
    Прямая публикация в RabbitMQ из бизнес-логики ненадёжна:
    - Если упадём после COMMIT БД, но до publish - событие потеряется.
    - Если RabbitMQ недоступен - бизнес-операция упадёт.

    Outbox решает обе проблемы: событие записывается в эту таблицу
    в той же транзакции, что и бизнес-данные (лид). Отдельный воркер
    (publisher_worker.py) асинхронно вычитывает unpublished события
    и публикует их в RabbitMQ exchange 'crm_events'.

Гарантии:
    - At-least-once: событие будет опубликовано хотя бы один раз
      (consumer'ы должны быть идемпотентны через processed_events).
    - Атомарность: бизнес-данные и событие коммитятся вместе или никак.
    - Порядок: события одного агрегата публикуются по created_at FIFO.

Публикуемые события: lead.created, lead.status_changed, lead.converted.
Модель идентична EventOutbox других сервисов проекта - единый паттерн.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventOutbox(Base):
    """Транзакционный outbox для событий CRM Service."""

    __tablename__ = "event_outbox"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    # Уникальный ID события - для идемпотентности на стороне consumer.
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )

    # Тип агрегата ('lead') и его ID - для аудита и фильтрации.
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Тип события: lead.created, lead.status_changed, lead.converted.
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)

    # Routing key для RabbitMQ - совпадает с event_type, хранится отдельно
    # на случай, если когда-то они разойдутся.
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)

    # Полная сериализованная нагрузка события (JSON).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Когда событие записано в outbox (момент бизнес-операции).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Когда воркер успешно опубликовал событие. NULL = ещё не опубликовано.
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Сколько раз воркер пытался опубликовать. При достижении max_attempts
    # событие считается dead-letter и пропускается (разбор через логи).
    published_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Последняя ошибка публикации - для диагностики.
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EventOutbox(id={self.id}, event_type={self.event_type}, "
            f"published={self.published_at is not None})>"
        )
"""
Outbox для надёжной публикации событий из Admin Service.

Публикуемые события: studio.created, studio.updated, studio.deactivated,
classroom.created, classroom.updated, classroom.deactivated.

Логика та же что в Auth и Schedule сервисах: событие пишется в эту
таблицу в той же транзакции, что и бизнес-данные. Отдельный воркер
(publisher_worker.py) асинхронно вычитывает unpublished события и
публикует их в RabbitMQ exchange 'admin_events'.

Гарантии:
    - At-least-once: событие будет опубликовано хотя бы один раз
      (consumer'ы должны быть идемпотентны через processed_events).
    - Атомарность: бизнес-данные и событие коммитятся вместе или никак.
    - Порядок: события одного агрегата публикуются по created_at FIFO.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventOutbox(Base):
    """
    Транзакционный outbox для событий Admin Service.
    """
    
    __tablename__ = "event_outbox"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Уникальный ID события - для идемпотентности на стороне consumer.
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    
    # Тип агрегата ('studio', 'classroom') и его ID.
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Тип события: studio.created, classroom.updated и т.п.
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Routing key для RabbitMQ - совпадает с event_type.
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Полная сериализованная нагрузка события (JSON).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # Когда событие было записано в outbox (момент бизнес-операции).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Когда воркер успешно опубликовал событие в RabbitMQ.
    # NULL = ещё не опубликовано.
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Сколько раз воркер пытался опубликовать.
    published_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    
    # Последняя ошибка публикации (для диагностики).
    last_error: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    
    __table_args__ = (
        # Partial-индекс по published_at IS NULL - воркер ищет именно
        # неопубликованные события, и такой индекс остаётся компактным
        # даже после миллионов опубликованных строк.
        Index(
            "ix_event_outbox_admin_unpublished",
            "created_at",
            postgresql_where=(published_at.is_(None)),
        ),
        # Для аудита и поиска событий по агрегату.
        Index(
            "ix_event_outbox_admin_aggregate",
            "aggregate_type",
            "aggregate_id",
        ),
    )
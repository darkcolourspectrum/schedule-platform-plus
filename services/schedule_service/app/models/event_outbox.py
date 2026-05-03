"""
Outbox для надёжной публикации событий из Schedule Service.

Зачем нужен:
    Прямая публикация в RabbitMQ из бизнес-логики ненадёжна:
    - Если упадём после COMMIT БД, но до publish - событие потеряется.
    - Если RabbitMQ недоступен - бизнес-операция упадёт.
    
    Outbox решает обе проблемы: событие записывается в эту таблицу
    в той же транзакции, что и бизнес-данные. Отдельный воркер
    (publisher_worker.py) асинхронно вычитывает unpublished события
    и публикует их в RabbitMQ.

Гарантии:
    - At-least-once: событие будет опубликовано хотя бы один раз
      (consumer'ы должны быть идемпотентны через processed_events).
    - Атомарность: бизнес-данные и событие коммитятся вместе или никак.
    - Порядок: события одного агрегата публикуются по created_at FIFO.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventOutbox(Base):
    """
    Транзакционный outbox для событий Schedule Service.
    
    Публикуемые события: lesson.created, lesson.updated, lesson.cancelled
    (последние два - на будущее).
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
    
    # Тип агрегата и его ID - для аудита и для возможной фильтрации.
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Тип события (lesson.created и т.п.) - для логирования и метрик.
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Routing key для RabbitMQ - совпадает с event_type, но хранится отдельно
    # на случай, если когда-то они разойдутся (разные подписки).
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Полная сериализованная нагрузка события (JSON).
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Когда событие было записано в outbox (момент бизнес-операции).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Когда воркер успешно опубликовал событие в RabbitMQ.
    # NULL = ещё не опубликовано, нужно публиковать.
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Сколько раз воркер пытался опубликовать.
    # При достижении max_attempts событие считается dead-letter
    # и пропускается (нужна ручная разборка через логи/мониторинг).
    published_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    
    # Текст последней ошибки публикации - для диагностики.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    def __repr__(self) -> str:
        return (
            f"<EventOutbox(id={self.id}, event_type={self.event_type}, "
            f"aggregate={self.aggregate_type}:{self.aggregate_id}, "
            f"published={'yes' if self.published_at else 'no'})>"
        )
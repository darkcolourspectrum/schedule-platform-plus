"""
Модель Transactional Outbox для надёжной публикации событий в RabbitMQ.

Паттерн:
    1. В одной транзакции с бизнес-операцией (создание/обновление пользователя)
       записываем событие в таблицу event_outbox.
    2. Фоновый воркер периодически читает строки с published_at IS NULL,
       публикует их в RabbitMQ и проставляет published_at.
    3. Это даёт at-least-once гарантию доставки: даже если RabbitMQ
       недоступен в момент бизнес-операции, событие не будет потеряно.

Consumer'ы должны быть идемпотентны (проверять event_id перед обработкой).
"""

from datetime import datetime
from typing import Optional, Any
from uuid import UUID, uuid4

from sqlalchemy import String, Integer, BigInteger, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventOutbox(Base):
    """
    Outbox-запись события для надёжной публикации в message broker.
    
    Жизненный цикл записи:
        - INSERT в той же транзакции, что и бизнес-операция (published_at = NULL)
        - SELECT воркером по индексу (published_at IS NULL ORDER BY created_at)
        - UPDATE published_at после успешной публикации в RabbitMQ
        - При ошибке публикации published_attempts инкрементируется,
          published_at остаётся NULL, запись будет повторно обработана
    
    Удаление обработанных записей выполняется отдельным retention-воркером
    (TTL ~7 дней), чтобы оставалась возможность аудита и переотправки.
    """
    
    __tablename__ = "event_outbox"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Глобальный идентификатор события. Попадает в payload и используется
    # consumer'ами для идемпотентности (дедупликации).
    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        comment="Глобальный UUID события для идемпотентности на стороне consumer"
    )
    
    # Тип агрегата, к которому относится событие. Полезно для фильтрации
    # и партиционирования в будущем (user, role, studio).
    aggregate_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Тип бизнес-сущности: user, role, studio"
    )
    
    # Идентификатор конкретной сущности. Хранится строкой, чтобы поддержать
    # как числовые, так и UUID-первичные ключи в разных агрегатах.
    aggregate_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="ID сущности агрегата (например, user_id)"
    )
    
    # Тип события в формате 'domain.action': user.created, user.updated,
    # user.deactivated, role.changed.
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Тип события, например user.created"
    )
    
    # Routing key для RabbitMQ. В большинстве случаев совпадает с event_type,
    # но вынесен отдельно для гибкости (можно публиковать в специфичный routing
    # без изменения event_type в payload).
    routing_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Routing key для публикации в topic exchange"
    )
    
    # Полное тело события в JSONB. Должно включать event_id, event_type,
    # schema_version, occurred_at и доменные данные.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Сериализованное тело события (JSON)"
    )
    
    # Когда событие было записано в outbox. Используется воркером для
    # упорядоченной обработки (FIFO внутри агрегата).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Время записи события в outbox"
    )
    
    # NULL = ещё не опубликовано. Заполняется воркером после успешного
    # publish в RabbitMQ. Воркер ищет именно по этому полю.
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время успешной публикации в message broker"
    )
    
    # Счётчик попыток публикации. Инкрементируется воркером при каждой
    # попытке. Нужен для:
    #   - метрик и алертов (если attempts > N — событие застряло)
    #   - circuit breaker (отказаться от попыток после M неудач)
    published_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Количество попыток публикации"
    )
    
    # Последняя ошибка публикации (для диагностики). Хранится текстом,
    # обнуляется при успешной публикации.
    last_error: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Текст последней ошибки публикации, если была"
    )
    
    __table_args__ = (
        # Главный индекс воркера: ищем неопубликованные события в порядке
        # их создания. Partial-индекс по published_at IS NULL экономит место
        # и держит индекс компактным даже на миллионах опубликованных строк.
        Index(
            "ix_event_outbox_unpublished",
            "created_at",
            postgresql_where=(published_at.is_(None))
        ),
        # Для аудита и поиска событий конкретного агрегата.
        Index("ix_event_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )
    
    def __repr__(self) -> str:
        status = "published" if self.published_at else "pending"
        return (
            f"<EventOutbox(id={self.id}, event_type={self.event_type}, "
            f"aggregate={self.aggregate_type}:{self.aggregate_id}, status={status})>"
        )
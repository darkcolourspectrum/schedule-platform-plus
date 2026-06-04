"""
Модель LeadStatusTransition - неизменяемый лог переходов статусов лида.

Назначение: основа для динамики воронки во времени и для метрики скорости
прохождения этапов. В отличие от lead_facts (один ряд на лид, текущее
состояние, перезаписывается) - здесь много рядов на лид, append-only,
никогда не редактируется.

Источник: событие 'lead.status_changed' из CRM ('crm_events'). Каждое
событие даёт одну запись перехода: from_status -> to_status в момент
occurred_at.

Из чего считается:
    - динамика "сколько лидов перешло в статус X по дням";
    - скорость воронки: разница occurred_at между переходами одного лида
      (например, среднее время new -> converted);
    - конверсии по дням: COUNT to_status='converted' GROUP BY день.

Почему append-only без updated_at: переход - это факт в прошлом, он не
меняется. Поэтому модель не наследует TimestampMixin (у которого есть
updated_at/onupdate) - только собственный occurred_at + synced_at.

Дедупликация: уникальность гарантирует event_id из processed_events на
уровне consumer'а. Здесь дополнительно держим source_event_id с UNIQUE -
вторая линия защиты от двойной вставки одного перехода при ретрае.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LeadStatusTransition(Base):
    """Одна запись перехода статуса лида. Append-only."""

    __tablename__ = "lead_status_transitions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Лид, к которому относится переход. Без FK: leads живут в
    # crm_service_db (кросс-БД FK невозможен, паттерн уже принят в проекте).
    lead_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    # Откуда перешли. NULL допустим для самого первого перехода, если
    # источник его так пометит (обычно первый статус 'new' приходит как
    # lead.created, а не как transition, но оставляем гибкость).
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Куда перешли. Всегда заполнено.
    to_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # Источник заявки лида на момент перехода. Денормализован сюда из
    # lead_facts, чтобы динамику можно было резать по источнику без JOIN.
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Студия лида. Денормализована по той же причине - разрез динамики
    # по филиалу без JOIN в lead_facts.
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # user_id админа, инициировавшего переход (changed_by из события).
    # NULL для системных переходов без инициатора-человека.
    changed_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Когда переход произошёл (бизнес-время из occurred_at события).
    # Главная ось для всех временных агрегаций.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # event_id породившего события. UNIQUE - вторая линия защиты от дублей
    # сверх processed_events: даже при гонке двух обработчиков одного
    # события БД не даст вставить переход дважды.
    source_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
    )

    # Когда запись попала в проекцию.
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        # Под основной запрос динамики: переходы в конкретный статус во
        # времени (например, конверсии по дням).
        Index(
            "ix_lead_transitions_to_status_time",
            "to_status",
            "occurred_at",
        ),
        # Под расчёт скорости воронки: все переходы лида по порядку времени.
        Index(
            "ix_lead_transitions_lead_time",
            "lead_id",
            "occurred_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LeadStatusTransition(lead_id={self.lead_id}, "
            f"{self.from_status}->{self.to_status} at {self.occurred_at})>"
        )
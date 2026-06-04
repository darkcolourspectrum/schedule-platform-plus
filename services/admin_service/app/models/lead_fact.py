"""
Модель LeadFact - аналитическая проекция текущего состояния лида.

Назначение: read-модель для дашборда администратора. Наполняется
consumer'ом событий CRM Service ('crm_events': lead.created,
lead.status_changed, lead.converted). Из неё считается текущая воронка
(сколько лидов в каждом статусе сейчас), разрез по источникам и причинам
потерь.

READ-ONLY для бизнес-логики: запись делает только аналитический consumer
(app/messaging/analytics_handlers.py). Дашборд читает через
AnalyticsRepository.

Почему отдельная таблица, а не обращение в crm_service_db: лиды живут
в изолированной БД CRM. Кросс-БД запросы запрещены архитектурой проекта.
Локальная проекция позволяет admin-сервису строить аналитику из одной
своей БД без синхронных HTTP-вызовов и без зависимости от живости CRM.

Связь с lead_status_transitions: эта таблица хранит ТЕКУЩЕЕ состояние
(один ряд на лид, перезаписывается), а lead_status_transitions - полную
неизменяемую историю переходов (много рядов на лид). Снимок воронки
берётся отсюда, динамика во времени - из transitions.

id здесь = lead_id из CRM. Своего autoincrement нет: проекция повторяет
первичный ключ источника, чтобы upsert по событию был тривиальным.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LeadFact(Base):
    """Текущее состояние лида - проекция для аналитики воронки."""

    __tablename__ = "lead_facts"

    # id совпадает с Lead.id в crm_service_db. autoincrement выключен:
    # ключ приходит из события, мы его не генерируем.
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )

    # Источник заявки: landing / instagram / referral / manual.
    # Значения берутся из CRM (LeadSource). CHECK-констрейнт здесь не
    # ставим намеренно: admin-сервис не должен знать enum CRM и ломаться
    # при добавлении нового источника в CRM. Допустимость значения - забота
    # источника. Это read-модель, она принимает то, что прислал источник.
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Текущий статус воронки: new / contacted / trial_scheduled /
    # trial_attended / converted / lost.
    current_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # Студия, на которую целилась заявка. NULL если на лендинге не было
    # выбора филиала. Для разреза воронки по студиям.
    studio_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    # user_id админа-ответственного. NULL если лид никому не назначен.
    # Для разреза "эффективность по ответственным".
    assigned_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Причина проигрыша - заполнена только у лидов в статусе 'lost'.
    # Для аналитики "почему теряем клиентов".
    lost_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # converted_user_id из CRM. Заполнен только у сконвертированных лидов.
    # Маркер успешной конверсии в клиента.
    converted_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Флаг "лид сконвертирован". Дублирует converted_user_id IS NOT NULL,
    # но как отдельная колонка даёт быстрый и читаемый фильтр в агрегатах
    # без выражения в WHERE.
    is_converted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Когда лид был создан в CRM (бизнес-время из lead.created.occurred_at,
    # а при backfill - из Lead.created_at). Основа для динамики "новых
    # лидов за период".
    lead_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Когда лид был сконвертирован. NULL у несконвертированных. Для метрики
    # скорости конверсии (converted_at - lead_created_at) и динамики
    # конверсий по дням.
    converted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # occurred_at последнего применённого события. Используется для
    # out-of-order защиты: апдейт применяется только если он новее
    # (тот же приём, что в users_cache/studios_cache).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события",
    )

    # Когда запись впервые попала в аналитическую проекцию.
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Когда запись впервые появилась в lead_facts",
    )

    __table_args__ = (
        # Композитный индекс под основной запрос воронки: распределение по
        # статусам в окне дат создания.
        Index(
            "ix_lead_facts_status_created",
            "current_status",
            "lead_created_at",
        ),
        # Под разрез воронки по источникам в окне дат.
        Index(
            "ix_lead_facts_source_created",
            "source",
            "lead_created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LeadFact(id={self.id}, status={self.current_status}, "
            f"source={self.source})>"
        )
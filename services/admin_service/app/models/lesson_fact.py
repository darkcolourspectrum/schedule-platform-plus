"""
Модель LessonFact - аналитическая проекция занятия для дашборда.

Назначение: операционная аналитика расписания - количество занятий по
преподавателям и студиям, доля отмен, динамика занятий во времени.
Наполняется consumer'ом событий Schedule Service ('schedule_events':
lesson.created, lesson.cancelled, lesson.rescheduled).

READ-ONLY для бизнес-логики: запись делает только аналитический consumer.
Дашборд читает через AnalyticsRepository.

Перенос НЕ равен отмене - ключевое архитектурное решение:
    Событие lesson.rescheduled меняет дату/время занятия, но занятие
    остаётся состоявшимся в воронке. Поэтому перенос НЕ выставляет
    cancelled_at и НЕ влияет на метрику "доля отмен". Он лишь обновляет
    дату занятия и инкрементирует rescheduled_count. Так "доля отмен"
    меряет именно отмены, а переносы видны отдельной метрикой
    "сколько занятий переносили".

Гранулярность времени: lesson_date - дата проведения занятия (ось для
"занятий за период"); created_at - когда занятие было заведено в системе;
cancelled_at - когда отменено. Все три нужны для разных срезов.

id здесь = lesson_id из Schedule. Своего autoincrement нет - проекция
повторяет первичный ключ источника.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LessonFact(Base):
    """Проекция занятия для операционной аналитики."""

    __tablename__ = "lesson_facts"

    # id совпадает с Lesson.id в schedule_service_db. autoincrement выключен.
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )

    # Преподаватель занятия. Для разреза "занятий на преподавателя".
    teacher_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    # Студия занятия. Для разреза по филиалам.
    studio_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Кабинет. NULL для онлайн-занятий. Под будущую метрику загрузки
    # кабинетов.
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Текущий статус занятия: scheduled / completed / cancelled / missed.
    # Источник истины - Schedule. Тут отражаем последнее известное значение.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Дата проведения занятия. Главная ось для "занятий за период"
    # (отличается от created_at - даты заведения в системе).
    lesson_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Сколько учеников было на занятии (длина student_ids из события).
    # Для оценки наполняемости и групповых занятий.
    student_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Сколько раз занятие переносили. Инкрементируется на каждый
    # lesson.rescheduled. НЕ связано с отменами.
    rescheduled_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Причина отмены - заполнена только у отменённых занятий.
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )

    # Когда занятие было заведено в системе (lesson.created.occurred_at,
    # при backfill - Lesson.created_at).
    lesson_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Когда занятие отменили. NULL у неотменённых. Заполняется по
    # lesson.cancelled. По этому полю строится динамика отмен. Перенос
    # сюда НИЧЕГО не пишет - это не отмена.
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # occurred_at последнего применённого события - out-of-order защита.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события",
    )

    # Когда запись впервые появилась в проекции.
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        # Под основной запрос: занятия преподавателя за период.
        Index(
            "ix_lesson_facts_teacher_date",
            "teacher_id",
            "lesson_date",
        ),
        # Под "доля отмен по студии за период".
        Index(
            "ix_lesson_facts_studio_status_date",
            "studio_id",
            "status",
            "lesson_date",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LessonFact(id={self.id}, teacher_id={self.teacher_id}, "
            f"status={self.status}, date={self.lesson_date})>"
        )
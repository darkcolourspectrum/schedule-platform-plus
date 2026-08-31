"""
Модель слота повторяющегося занятия.

Слот - это одно правило "когда" внутри шаблона: день недели, время начала,
длительность и кабинет. Шаблон (RecurringPattern) отвечает за "кто с кем и
в какой период", слоты - за "когда именно".

Зачем разделение:
    Раньше шаблон нёс ровно один день недели и одно время, поэтому
    "вторник 18:00 и четверг 19:30" требовало двух независимых шаблонов
    с продублированным списком учеников и периодом действия. Расхождение
    между такими шаблонами (разные valid_until, разный состав учеников)
    было вопросом времени.

    Со слотами это один шаблон с двумя строками. Ученики, период действия
    и периодичность заданы один раз и физически не могут разойтись.

Кабинет живёт в слоте, а не в шапке, намеренно: во вторник занятие может
идти в первом кабинете, а в четверг в третьем - это нормальная ситуация
для студии, где преподаватель подстраивается под свободные помещения.

Ограничения:
    - day_of_week проверяется на уровне БД (1-7). Без этого генератор
      мог зациклиться навсегда, подбирая несуществующий день недели.
    - duration_minutes ограничена сверху 480 минутами (8 часов) - это
      не бизнес-правило, а предохранитель от опечатки в форме.
    - Уникальность (шаблон, день, время) не даёт завести два одинаковых
      слота. Пересечение слотов с РАЗНЫМ временем внутри одного шаблона
      (вторник 18:00 60 мин и вторник 18:30) констрейнтом не ловится -
      это проверка сервисного слоя.
"""

from typing import Optional, TYPE_CHECKING
from datetime import time

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.recurring_pattern import RecurringPattern

class RecurringPatternSlot(Base, TimestampMixin):
    """Одно правило повторения внутри шаблона: день недели + время."""

    __tablename__ = "recurring_pattern_slots"
    __table_args__ = (
        UniqueConstraint(
            "recurring_pattern_id",
            "day_of_week",
            "start_time",
            name="uq_pattern_slot_day_time",
        ),
        CheckConstraint(
            "day_of_week BETWEEN 1 AND 7",
            name="ck_pattern_slot_day_of_week",
        ),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 480",
            name="ck_pattern_slot_duration",
        ),
        Index("ix_pattern_slots_pattern_id", "recurring_pattern_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    recurring_pattern_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_patterns.id", ondelete="CASCADE"),
        nullable=False,
    )

    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1=Понедельник, 2=Вторник, ..., 7=Воскресенье (ISO)",
    )

    start_time: Mapped[time] = mapped_column(Time, nullable=False)

    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
        comment="Длительность занятия в минутах",
    )

    # NULL = занятие без кабинета (онлайн). Проверка конфликта кабинета
    # для таких занятий не выполняется, конфликт преподавателя - выполняется.
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    pattern: Mapped["RecurringPattern"] = relationship(
        "RecurringPattern",
        back_populates="slots",
    )

    def __repr__(self) -> str:
        return (
            f"<RecurringPatternSlot(id={self.id}, "
            f"pattern_id={self.recurring_pattern_id}, "
            f"day={self.day_of_week}, time={self.start_time})>"
        )
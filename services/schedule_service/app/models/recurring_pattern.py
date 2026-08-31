"""
Модель шаблона повторяющегося занятия
"""

from typing import Optional, TYPE_CHECKING
from datetime import date
from sqlalchemy import Integer, Boolean, Date, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.lesson import Lesson
    from app.models.lesson_student import RecurringPatternStudent
    from app.models.recurring_pattern_slot import RecurringPatternSlot

class RecurringPattern(Base, TimestampMixin):
    """
    Шаблон повторяющегося занятия
    
    Описывает правило: "Каждый понедельник в 10:00 с учеником X в кабинете Y"
    На основе этого шаблона автоматически генерируются конкретные занятия
    """
    
    __tablename__ = "recurring_patterns"

    __table_args__ = (
        CheckConstraint(
            "week_interval IN (1, 2)",
            name="ck_pattern_week_interval",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_pattern_valid_range",
        ),
    )
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Привязка к студии и преподавателю
    studio_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Период действия шаблона
    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="С какой даты начинает действовать шаблон"
    )
    
    valid_until: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="До какой даты действует (NULL = бессрочно)"
    )

    week_interval: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="1 = каждую неделю, 2 = раз в две недели",
    )

    anchor_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment=(
            "Опорная дата для расчёта чётности недели при week_interval=2. "
            "Фиксируется при создании и не меняется при правке valid_from"
        ),
    )
    
    # Статус
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Активен ли шаблон"
    )
    
    # Дополнительная информация
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    slots: Mapped[list["RecurringPatternSlot"]] = relationship(
        "RecurringPatternSlot",
        back_populates="pattern",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    lessons: Mapped[list["Lesson"]] = relationship(
        "Lesson",
        back_populates="recurring_pattern",
        passive_deletes=True,
    )
    
    students: Mapped[list["RecurringPatternStudent"]] = relationship(
        "RecurringPatternStudent",
        back_populates="pattern",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return (
            f"<RecurringPattern(id={self.id}, teacher_id={self.teacher_id}, "
            f"interval={self.week_interval}w, active={self.is_active})>"
        )

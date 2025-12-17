"""
Модель шаблона повторяющегося занятия
"""

from typing import Optional
from datetime import date, time
from sqlalchemy import String, Integer, Boolean, Date, Time, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RecurringPattern(Base, TimestampMixin):
    """
    Шаблон повторяющегося занятия
    
    Описывает правило: "Каждый понедельник в 10:00 с учеником X в кабинете Y"
    На основе этого шаблона автоматически генерируются конкретные занятия
    """
    
    __tablename__ = "recurring_patterns"
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Привязка к студии и преподавателю
    studio_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Кабинет (может быть NULL для онлайн-занятий)
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Правило повторения
    day_of_week: Mapped[int] = mapped_column(
        Integer, 
        nullable=False,
        comment="1=Понедельник, 2=Вторник, ..., 7=Воскресенье"
    )
    
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
        comment="Длительность занятия в минутах"
    )
    
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
    lessons: Mapped[list["Lesson"]] = relationship(
        "Lesson",
        back_populates="recurring_pattern",
        cascade="all, delete-orphan"
    )
    
    students: Mapped[list["RecurringPatternStudent"]] = relationship(
        "RecurringPatternStudent",
        back_populates="pattern",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<RecurringPattern(id={self.id}, teacher_id={self.teacher_id}, day={self.day_of_week}, time={self.start_time})>"

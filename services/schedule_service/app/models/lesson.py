"""
Модель конкретного занятия
"""

from typing import Optional
from datetime import date, time
from sqlalchemy import String, Integer, Date, Time, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Lesson(Base, TimestampMixin):
    """
    Конкретное занятие в определенную дату и время
    
    Может быть создано:
    1. Автоматически из recurring_pattern (recurring_pattern_id != NULL)
    2. Вручную как разовое занятие (recurring_pattern_id = NULL)
    """
    
    __tablename__ = "lessons"
    __table_args__ = (
        Index('idx_studio_date', 'studio_id', 'lesson_date'),
        Index('idx_teacher_date', 'teacher_id', 'lesson_date'),
        Index('idx_classroom_datetime', 'classroom_id', 'lesson_date', 'start_time'),
        Index('idx_status', 'status'),
    )
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Привязка к студии и преподавателю
    studio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Кабинет (может быть NULL для онлайн)
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Связь с шаблоном (если есть)
    recurring_pattern_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recurring_patterns.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL = разовое занятие, иначе - сгенерировано из шаблона"
    )
    
    # Дата и время занятия
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    
    # Статус занятия
    status: Mapped[str] = mapped_column(
        String(20),
        default="scheduled",
        nullable=False,
        comment="scheduled, completed, cancelled, missed"
    )
    
    # Дополнительная информация
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Заметки преподавателя"
    )
    
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Причина отмены"
    )
    
    # Relationships
    recurring_pattern: Mapped[Optional["RecurringPattern"]] = relationship(
        "RecurringPattern",
        back_populates="lessons"
    )
    
    students: Mapped[list["LessonStudent"]] = relationship(
        "LessonStudent",
        back_populates="lesson",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Lesson(id={self.id}, date={self.lesson_date}, time={self.start_time}, status={self.status})>"

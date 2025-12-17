"""
Модели связей занятий и шаблонов с учениками
"""

from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class LessonStudent(Base, TimestampMixin):
    """
    Связь конкретного занятия с учеником
    
    Позволяет:
    - Отслеживать какие ученики на занятии (для групповых)
    - Отмечать посещаемость каждого ученика отдельно
    """
    
    __tablename__ = "lesson_students"
    __table_args__ = (
        UniqueConstraint('lesson_id', 'student_id', name='uq_lesson_student'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    student_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True
    )
    
    # Статус участия ученика
    attendance_status: Mapped[str] = mapped_column(
        String(20),
        default="scheduled",
        nullable=False,
        comment="scheduled, attended, missed, cancelled"
    )
    
    # Relationships
    lesson: Mapped["Lesson"] = relationship(
        "Lesson",
        back_populates="students"
    )
    
    def __repr__(self) -> str:
        return f"<LessonStudent(lesson_id={self.lesson_id}, student_id={self.student_id}, status={self.attendance_status})>"


class RecurringPatternStudent(Base, TimestampMixin):
    """
    Связь шаблона повторяющегося занятия с учеником
    
    При генерации занятий из шаблона, ученики автоматически
    копируются в lesson_students для каждого созданного занятия
    """
    
    __tablename__ = "recurring_pattern_students"
    __table_args__ = (
        UniqueConstraint('recurring_pattern_id', 'student_id', name='uq_pattern_student'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    recurring_pattern_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_patterns.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    student_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True
    )
    
    # Relationships
    pattern: Mapped["RecurringPattern"] = relationship(
        "RecurringPattern",
        back_populates="students"
    )
    
    def __repr__(self) -> str:
        return f"<RecurringPatternStudent(pattern_id={self.recurring_pattern_id}, student_id={self.student_id})>"

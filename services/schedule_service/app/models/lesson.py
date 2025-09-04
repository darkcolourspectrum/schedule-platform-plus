from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, ForeignKey, Integer, Boolean, JSON
from typing import List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.time_slot import TimeSlot


class LessonStatus(str, Enum):
    """Статус урока вокальной школы"""
    SCHEDULED = "scheduled"     # Запланирован
    CONFIRMED = "confirmed"     # Подтвержден учеником
    IN_PROGRESS = "in_progress" # Урок проходит
    COMPLETED = "completed"     # Урок завершен
    CANCELLED = "cancelled"     # Отменен
    NO_SHOW = "no_show"        # Ученик не пришел


class LessonType(str, Enum):
    """Типы уроков вокала"""
    INDIVIDUAL = "individual"   # Индивидуальный урок
    GROUP = "group"            # Групповой урок 
    TRIAL = "trial"            # Пробный урок
    MAKEUP = "makeup"          # Отработка пропущенного урока


class Lesson(Base, TimestampMixin):
    """
    Урок вокала, привязанный к временному слоту
    
    Создается преподавателем после бронирования TimeSlot
    """
    
    __tablename__ = "lessons"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Основная информация урока
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    lesson_type: Mapped[LessonType] = mapped_column(default=LessonType.INDIVIDUAL, nullable=False)
    status: Mapped[LessonStatus] = mapped_column(default=LessonStatus.SCHEDULED, nullable=False)
    
    # Описание и заметки
    description: Mapped[str] = mapped_column(Text, nullable=True)
    teacher_notes: Mapped[str] = mapped_column(Text, nullable=True)
    homework: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Преподаватель (данные дублируются из Auth Service для производительности)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_name: Mapped[str] = mapped_column(String(200), nullable=False)
    teacher_email: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Ученики урока (JSON массив для гибкости групповых уроков)
    students: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # Структура: [{"id": int, "name": str, "email": str, "phone": str, "level": str}, ...]
    
    # Настройки урока
    max_students: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_trial_lesson: Mapped[bool] = mapped_column(Boolean, default=False)
    is_makeup_lesson: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Отмена урока
    cancelled_by_teacher: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_by_student: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_reason: Mapped[str] = mapped_column(String(500), nullable=True)
    
    # Связь с временным слотом (один к одному)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id"), nullable=False, unique=True)
    
    # Отношения
    time_slot: Mapped["TimeSlot"] = relationship("TimeSlot", back_populates="lesson")
    
    def __repr__(self) -> str:
        return f"<Lesson(id={self.id}, title='{self.title}', type='{self.lesson_type}', teacher='{self.teacher_name}')>"
    
    @property
    def start_time(self) -> datetime:
        """Время начала урока (из временного слота)"""
        return self.time_slot.datetime_start
    
    @property
    def end_time(self) -> datetime:
        """Время окончания урока (из временного слота)"""
        return self.time_slot.datetime_end
    
    @property
    def duration_minutes(self) -> int:
        """Длительность урока в минутах"""
        return self.time_slot.duration_minutes
    
    @property
    def date_str(self) -> str:
        """Дата урока в строке"""
        return self.time_slot.date.strftime("%Y-%m-%d")
    
    @property
    def time_range_str(self) -> str:
        """Временной диапазон урока в строке"""
        return f"{self.time_slot.start_time.strftime('%H:%M')}-{self.time_slot.end_time.strftime('%H:%M')}"
    
    @property
    def full_datetime_range(self) -> str:
        """Полная дата и время урока"""
        return f"{self.date_str} {self.time_range_str}"
    
    @property
    def students_count(self) -> int:
        """Количество записанных учеников"""
        return len(self.students)
    
    @property
    def can_add_student(self) -> bool:
        """Можно ли добавить ученика"""
        return self.students_count < self.max_students and self.status in [LessonStatus.SCHEDULED, LessonStatus.CONFIRMED]
    
    @property
    def is_group_lesson(self) -> bool:
        """Является ли урок групповым"""
        return self.lesson_type == LessonType.GROUP or self.max_students > 1
    
    @property
    def can_be_cancelled(self) -> bool:
        """Можно ли отменить урок"""
        if self.status in [LessonStatus.COMPLETED, LessonStatus.CANCELLED]:
            return False
        return self.time_slot.can_be_cancelled
    
    def add_student(self, student_data: Dict[str, Any]) -> None:
        """Добавление ученика к уроку"""
        if not self.can_add_student:
            raise ValueError("Cannot add more students to this lesson")
        
        # Проверяем, что ученик еще не записан
        student_id = student_data.get('id')
        if any(s.get('id') == student_id for s in self.students):
            raise ValueError(f"Student with ID {student_id} is already enrolled")
        
        # Добавляем ученика
        self.students = self.students + [student_data]
        
        # Подтверждаем урок при добавлении первого ученика
        if self.status == LessonStatus.SCHEDULED:
            self.status = LessonStatus.CONFIRMED
    
    def remove_student(self, student_id: int) -> None:
        """Удаление ученика из урока"""
        original_count = len(self.students)
        self.students = [s for s in self.students if s.get('id') != student_id]
        
        if len(self.students) == original_count:
            raise ValueError(f"Student with ID {student_id} not found in lesson")
        
        # Если учеников не осталось, возвращаем статус "запланирован"
        if len(self.students) == 0 and self.status == LessonStatus.CONFIRMED:
            self.status = LessonStatus.SCHEDULED
    
    def cancel_lesson(self, reason: str, cancelled_by_teacher: bool = True) -> None:
        """Отмена урока"""
        if not self.can_be_cancelled:
            raise ValueError("This lesson cannot be cancelled")
        
        self.status = LessonStatus.CANCELLED
        self.cancellation_reason = reason
        
        if cancelled_by_teacher:
            self.cancelled_by_teacher = True
        else:
            self.cancelled_by_student = True
    
    def mark_as_no_show(self) -> None:
        """Отметить, что ученик не пришел"""
        if self.status not in [LessonStatus.CONFIRMED, LessonStatus.IN_PROGRESS]:
            raise ValueError("Can only mark confirmed or in-progress lessons as no-show")
        
        self.status = LessonStatus.NO_SHOW
    
    def start_lesson(self) -> None:
        """Начало урока"""
        if self.status != LessonStatus.CONFIRMED:
            raise ValueError("Can only start confirmed lessons")
        
        self.status = LessonStatus.IN_PROGRESS
    
    def complete_lesson(self, teacher_notes: str = None, homework: str = None) -> None:
        """Завершение урока"""
        if self.status != LessonStatus.IN_PROGRESS:
            raise ValueError("Can only complete lessons that are in progress")
        
        self.status = LessonStatus.COMPLETED
        
        if teacher_notes:
            self.teacher_notes = teacher_notes
        
        if homework:
            self.homework = homework
        
        # Обновляем статус временного слота
        self.time_slot.complete_lesson()
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
        """Временной диапазон урока"""
        return self.time_slot.time_range_str
    
    @property
    def studio_name(self) -> str:
        """Название студии"""
        return self.time_slot.studio.name
    
    @property
    def room_name(self) -> str:
        """Название кабинета"""
        return self.time_slot.room.name
    
    @property
    def student_count(self) -> int:
        """Количество записанных учеников"""
        return len(self.students)
    
    @property
    def is_group_lesson(self) -> bool:
        """Является ли урок групповым"""
        return self.student_count > 1
    
    @property
    def has_free_spots(self) -> bool:
        """Есть ли свободные места для учеников"""
        return self.student_count < self.max_students
    
    @property
    def students_names(self) -> List[str]:
        """Список имен учеников"""
        return [student.get("name", "Unknown") for student in self.students]
    
    @property
    def can_be_cancelled_by_teacher(self) -> bool:
        """Может ли преподаватель отменить урок"""
        if self.status in [LessonStatus.COMPLETED, LessonStatus.CANCELLED]:
            return False
        
        # Проверяем, что до начала урока осталось минимум 4 часа
        hours_until_lesson = (self.start_time - datetime.now()).total_seconds() / 3600
        return hours_until_lesson >= 4
    
    @property
    def can_be_cancelled_by_student(self) -> bool:
        """Может ли ученик отменить урок (большее время для отмены)"""
        if self.status in [LessonStatus.COMPLETED, LessonStatus.CANCELLED]:
            return False
        
        # Ученик должен отменить минимум за 1 час
        hours_until_lesson = (self.start_time - datetime.now()).total_seconds() / 3600
        return hours_until_lesson >= 1
    
    def add_student(self, student_id: int, name: str, email: str, phone: str = "", level: str = "beginner") -> bool:
        """
        Добавить ученика к уроку
        
        Args:
            student_id: ID ученика из Auth Service
            name: Имя ученика
            email: Email ученика
            phone: Телефон ученика
            level: Уровень ученика (beginner, intermediate, advanced)
            
        Returns:
            bool: True если ученик добавлен успешно
        """
        if not self.has_free_spots:
            return False
        
        # Проверяем, что ученик еще не записан на этот урок
        existing_ids = [student.get("id") for student in self.students]
        if student_id in existing_ids:
            return False
        
        student_data = {
            "id": student_id,
            "name": name,
            "email": email,
            "phone": phone,
            "level": level,
            "enrolled_at": datetime.now().isoformat()
        }
        
        self.students.append(student_data)
        
        # Автоматически обновляем тип урока
        if len(self.students) > 1 and self.lesson_type == LessonType.INDIVIDUAL:
            self.lesson_type = LessonType.GROUP
        
        # Если урок был только запланирован - переводим в подтвержденное состояние
        if self.status == LessonStatus.SCHEDULED:
            self.status = LessonStatus.CONFIRMED
        
        return True
    
    def remove_student(self, student_id: int) -> bool:
        """
        Удалить ученика из урока
        
        Args:
            student_id: ID ученика
            
        Returns:
            bool: True если ученик удален
        """
        original_count = len(self.students)
        self.students = [student for student in self.students if student.get("id") != student_id]
        
        if len(self.students) < original_count:
            # Обновляем тип урока если остался один ученик
            if len(self.students) == 1 and self.lesson_type == LessonType.GROUP:
                self.lesson_type = LessonType.INDIVIDUAL
            
            # Если не осталось учеников - возвращаем к запланированному статусу
            if len(self.students) == 0 and self.status == LessonStatus.CONFIRMED:
                self.status = LessonStatus.SCHEDULED
            
            return True
        
        return False
    
    def cancel_lesson(self, reason: str, by_teacher: bool = True, by_student: bool = False) -> bool:
        """
        Отменить урок
        
        Args:
            reason: Причина отмены
            by_teacher: Отменен преподавателем
            by_student: Отменен учеником
            
        Returns:
            bool: True если урок отменен
        """
        if not (self.can_be_cancelled_by_teacher if by_teacher else self.can_be_cancelled_by_student):
            return False
        
        self.status = LessonStatus.CANCELLED
        self.cancellation_reason = reason
        self.cancelled_by_teacher = by_teacher
        self.cancelled_by_student = by_student
        
        # Освобождаем временной слот
        self.time_slot.release_reservation(self.teacher_id)
        
        return True
    
    def complete_lesson(self, notes: str = "", homework: str = "") -> bool:
        """
        Завершить урок
        
        Args:
            notes: Заметки преподавателя о проведенном уроке
            homework: Домашнее задание
            
        Returns:
            bool: True если урок завершен
        """
        if self.status not in [LessonStatus.CONFIRMED, LessonStatus.IN_PROGRESS]:
            return False
        
        self.status = LessonStatus.COMPLETED
        if notes:
            self.teacher_notes = notes
        if homework:
            self.homework = homework
        
        # Отмечаем слот как завершенный
        self.time_slot.complete_lesson()
        
        return True
    
    def start_lesson(self) -> bool:
        """Начать урок (перевести в статус 'в процессе')"""
        if self.status == LessonStatus.CONFIRMED:
            self.status = LessonStatus.IN_PROGRESS
            return True
        return False
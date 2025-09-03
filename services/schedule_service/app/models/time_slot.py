from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Date, Time, ForeignKey, Integer, Boolean, String
from typing import Optional, TYPE_CHECKING
from datetime import datetime, date, time
from enum import Enum

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.studio import Studio
    from app.models.room import Room
    from app.models.lesson import Lesson


class SlotStatus(str, Enum):
    """Статус временного слота"""
    AVAILABLE = "available"       # Доступен для бронирования
    RESERVED = "reserved"        # Забронирован преподавателем (но урок еще не назначен)
    BOOKED = "booked"           # Забронирован с назначенным уроком
    BLOCKED = "blocked"         # Заблокирован администратором
    COMPLETED = "completed"     # Урок завершен


class TimeSlot(Base, TimestampMixin):
    """
    Временной слот - основная единица расписания
    
    Жизненный цикл слота:
    AVAILABLE -> RESERVED (преподаватель бронирует) -> BOOKED (добавляет урок и учеников) -> COMPLETED
    """
    
    __tablename__ = "time_slots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Время и дата
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Статус слота
    status: Mapped[SlotStatus] = mapped_column(default=SlotStatus.AVAILABLE, nullable=False)
    
    # Привязка к студии и кабинету
    studio_id: Mapped[int] = mapped_column(ForeignKey("studios.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    
    # Преподаватель, который забронировал слот (из Auth Service)
    reserved_by_teacher_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reserved_by_teacher_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reserved_by_teacher_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Заметки администратора (для заблокированных слотов)
    admin_notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Отношения
    studio: Mapped["Studio"] = relationship("Studio", back_populates="time_slots")
    room: Mapped["Room"] = relationship("Room", back_populates="time_slots")
    lesson: Mapped[Optional["Lesson"]] = relationship(
        "Lesson",
        back_populates="time_slot",
        uselist=False
    )
    
    def __repr__(self) -> str:
        return f"<TimeSlot(id={self.id}, date={self.date}, time={self.start_time}-{self.end_time}, status={self.status})>"
    
    @property
    def datetime_start(self) -> datetime:
        """Полная дата и время начала"""
        return datetime.combine(self.date, self.start_time)
    
    @property
    def datetime_end(self) -> datetime:
        """Полная дата и время окончания"""
        return datetime.combine(self.date, self.end_time)
    
    @property
    def is_available(self) -> bool:
        """Доступен ли слот для бронирования"""
        return self.status == SlotStatus.AVAILABLE and not self.is_past
    
    @property
    def is_reserved(self) -> bool:
        """Забронирован ли слот преподавателем"""
        return self.status == SlotStatus.RESERVED
    
    @property
    def is_booked(self) -> bool:
        """Полностью забронирован ли слот (с уроком)"""
        return self.status == SlotStatus.BOOKED and self.lesson is not None
    
    @property
    def is_past(self) -> bool:
        """Прошел ли временной слот"""
        return self.datetime_end < datetime.now()
    
    @property
    def time_range_str(self) -> str:
        """Временной диапазон в строке HH:MM-HH:MM"""
        return f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"
    
    @property
    def can_be_reserved_by_teacher(self, teacher_id: int) -> bool:
        """Может ли преподаватель забронировать этот слот"""
        return self.is_available
    
    @property
    def can_be_cancelled_by_teacher(self, teacher_id: int) -> bool:
        """Может ли преподаватель отменить бронирование"""
        if self.reserved_by_teacher_id != teacher_id:
            return False
        
        if self.status == SlotStatus.COMPLETED:
            return False
        
        # Можно отменить минимум за 2 часа до начала
        hours_until_slot = (self.datetime_start - datetime.now()).total_seconds() / 3600
        return hours_until_slot >= 2
    
    def reserve_for_teacher(self, teacher_id: int, teacher_name: str, teacher_email: str) -> bool:
        """
        Бронирование слота преподавателем
        
        Returns:
            bool: True если успешно забронировано
        """
        if not self.is_available:
            return False
        
        self.status = SlotStatus.RESERVED
        self.reserved_by_teacher_id = teacher_id
        self.reserved_by_teacher_name = teacher_name
        self.reserved_by_teacher_email = teacher_email
        return True
    
    def release_reservation(self, teacher_id: int) -> bool:
        """
        Снятие брони со слота преподавателем
        
        Args:
            teacher_id: ID преподавателя, который пытается снять бронь
            
        Returns:
            bool: True если бронь снята
        """
        if not self.can_be_cancelled_by_teacher(teacher_id):
            return False
        
        self.status = SlotStatus.AVAILABLE
        self.reserved_by_teacher_id = None
        self.reserved_by_teacher_name = None
        self.reserved_by_teacher_email = None
        return True
    
    def mark_as_booked(self) -> bool:
        """
        Отметить слот как полностью забронированный (с уроком)
        
        Returns:
            bool: True если статус изменен
        """
        if self.status == SlotStatus.RESERVED:
            self.status = SlotStatus.BOOKED
            return True
        return False
    
    def complete_lesson(self) -> bool:
        """
        Завершить урок в этом слоте
        
        Returns:
            bool: True если урок завершен
        """
        if self.status == SlotStatus.BOOKED:
            self.status = SlotStatus.COMPLETED
            return True
        return False
    
    def block_by_admin(self, reason: str) -> None:
        """Блокировка слота администратором"""
        self.status = SlotStatus.BLOCKED
        self.admin_notes = reason
    
    def unblock_by_admin(self) -> None:
        """Разблокировка слота администратором"""
        if self.status == SlotStatus.BLOCKED:
            self.status = SlotStatus.AVAILABLE
            self.admin_notes = None
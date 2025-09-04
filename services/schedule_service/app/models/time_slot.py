from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Date, Time, ForeignKey, Integer, Boolean, String
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from datetime import date as date_type, time as time_type  # Избегаем конфликта имен
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
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    start_time: Mapped[time_type] = mapped_column(Time, nullable=False)
    end_time: Mapped[time_type] = mapped_column(Time, nullable=False)
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
        """Забронирован ли слот с уроком"""
        return self.status == SlotStatus.BOOKED
    
    @property
    def is_past(self) -> bool:
        """Прошел ли слот по времени"""
        return datetime.now() > self.datetime_start
    
    @property
    def can_be_cancelled(self) -> bool:
        """Можно ли отменить бронирование"""
        if self.is_past:
            return False
        # Можно отменить за 2 часа до урока
        return (self.datetime_start - datetime.now()).total_seconds() > 7200  # 2 часа = 7200 секунд
    
    def reserve_for_teacher(self, teacher_id: int, teacher_name: str, teacher_email: str) -> None:
        """Бронирование слота для преподавателя"""
        if not self.is_available:
            raise ValueError(f"Slot is not available (status: {self.status})")
        
        self.status = SlotStatus.RESERVED
        self.reserved_by_teacher_id = teacher_id
        self.reserved_by_teacher_name = teacher_name
        self.reserved_by_teacher_email = teacher_email
    
    def release_from_teacher(self) -> None:
        """Освобождение слота от преподавателя"""
        if self.status not in [SlotStatus.RESERVED, SlotStatus.BOOKED]:
            raise ValueError(f"Cannot release slot with status: {self.status}")
        
        self.status = SlotStatus.AVAILABLE
        self.reserved_by_teacher_id = None
        self.reserved_by_teacher_name = None
        self.reserved_by_teacher_email = None
    
    def book_with_lesson(self) -> None:
        """Подтверждение бронирования с назначенным уроком"""
        if self.status != SlotStatus.RESERVED:
            raise ValueError(f"Cannot book slot with status: {self.status}")
        
        self.status = SlotStatus.BOOKED
    
    def complete_lesson(self) -> None:
        """Завершение урока"""
        if self.status != SlotStatus.BOOKED:
            raise ValueError(f"Cannot complete lesson for slot with status: {self.status}")
        
        self.status = SlotStatus.COMPLETED
    
    def block_slot(self, admin_notes: Optional[str] = None) -> None:
        """Блокировка слота администратором"""
        self.status = SlotStatus.BLOCKED
        self.admin_notes = admin_notes
    
    def unblock_slot(self) -> None:
        """Разблокировка слота"""
        if self.status != SlotStatus.BLOCKED:
            raise ValueError(f"Cannot unblock slot with status: {self.status}")
        
        self.status = SlotStatus.AVAILABLE
        self.admin_notes = None
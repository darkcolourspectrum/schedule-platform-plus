from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Boolean
from typing import List, TYPE_CHECKING

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.room import Room
    from app.models.time_slot import TimeSlot


class Studio(Base, TimestampMixin):
    """
    Модель студии вокальной школы
    Синхронизируется с данными из Auth Service
    """
    
    __tablename__ = "studios"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Основная информация (кэш из Auth Service для производительности)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Связь с Auth Service (для синхронизации данных)
    auth_service_studio_id: Mapped[int] = mapped_column(nullable=False, unique=True)
    
    # Настройки расписания для студии
    working_hours_start: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    working_hours_end: Mapped[str] = mapped_column(String(5), default="21:00", nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(default=60, nullable=False)  # Стандартная длительность слота
    
    # Отношения
    rooms: Mapped[List["Room"]] = relationship(
        "Room", 
        back_populates="studio",
        cascade="all, delete-orphan"
    )
    
    time_slots: Mapped[List["TimeSlot"]] = relationship(
        "TimeSlot",
        back_populates="studio"
    )
    
    def __repr__(self) -> str:
        return f"<Studio(id={self.id}, name='{self.name}')>"
    
    @property
    def working_hours_range(self) -> str:
        """Рабочие часы студии в формате '09:00-21:00'"""
        return f"{self.working_hours_start}-{self.working_hours_end}"
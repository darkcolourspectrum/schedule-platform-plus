from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Boolean, ForeignKey, Integer
from typing import List, TYPE_CHECKING
from enum import Enum

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.studio import Studio
    from app.models.time_slot import TimeSlot


class RoomType(str, Enum):
    """Типы кабинетов вокальной школы"""
    VOCAL_SMALL = "vocal_small"      # Малый вокальный класс (1-2 человека)
    VOCAL_LARGE = "vocal_large"      # Большой вокальный класс (группы до 6 человек)
    INSTRUMENTAL = "instrumental"     # Класс с инструментами
    RECORDING = "recording"          # Студия звукозаписи
    THEORY = "theory"               # Теоретический класс


class Room(Base, TimestampMixin):
    """Модель кабинета в вокальной студии"""
    
    __tablename__ = "rooms"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Основная информация
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    room_type: Mapped[RoomType] = mapped_column(default=RoomType.VOCAL_SMALL, nullable=False)
    
    # Вместимость и характеристики
    max_capacity: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    area_sqm: Mapped[int] = mapped_column(Integer, nullable=True)
    floor_number: Mapped[int] = mapped_column(Integer, default=1, nullable=True)
    
    # Оборудование для вокальных занятий
    has_piano: Mapped[bool] = mapped_column(Boolean, default=True)
    has_microphone: Mapped[bool] = mapped_column(Boolean, default=True)
    has_mirror: Mapped[bool] = mapped_column(Boolean, default=True)
    has_sound_system: Mapped[bool] = mapped_column(Boolean, default=True)
    has_recording_equipment: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Доступность
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Связь со студией
    studio_id: Mapped[int] = mapped_column(ForeignKey("studios.id"), nullable=False)
    
    # Отношения
    studio: Mapped["Studio"] = relationship("Studio", back_populates="rooms")
    time_slots: Mapped[List["TimeSlot"]] = relationship(
        "TimeSlot",
        back_populates="room"
    )
    
    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}', studio='{self.studio.name if self.studio else 'None'}')>"
    
    @property
    def full_name(self) -> str:
        """Полное название с указанием студии"""
        return f"{self.studio.name} - {self.name}" if self.studio else self.name
    
    @property
    def equipment_summary(self) -> str:
        """Краткое описание оборудования"""
        equipment = []
        if self.has_piano:
            equipment.append("фортепиано")
        if self.has_microphone:
            equipment.append("микрофон")
        if self.has_recording_equipment:
            equipment.append("запись")
        return ", ".join(equipment) if equipment else "базовое оборудование"
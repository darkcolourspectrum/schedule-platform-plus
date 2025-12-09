"""
Classroom model - Кабинеты в студиях
"""

from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.studio import Studio


class Classroom(Base, TimestampMixin):
    """
    Модель кабинета в студии
    
    Каждый кабинет принадлежит конкретной студии
    В кабинете проходят уроки
    """
    
    __tablename__ = "classrooms"
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True)
    
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID студии"
    )
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Название кабинета"
    )
    
    # Характеристики
    capacity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Вместимость кабинета (количество человек)"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание кабинета"
    )
    
    equipment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Оборудование в кабинете (микрофоны, пианино и т.д.)"
    )
    
    # Дополнительная информация
    floor: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Этаж"
    )
    
    room_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Номер кабинета"
    )
    
    # Статус
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Активен ли кабинет"
    )
    
    # Relationships
    studio: Mapped["Studio"] = relationship(
        "Studio",
        back_populates="classrooms",
        lazy="select"
    )
    
    def __repr__(self) -> str:
        return f"<Classroom(id={self.id}, name='{self.name}', studio_id={self.studio_id})>"
    
    def to_dict(self) -> dict:
        """Конвертация в словарь"""
        return {
            "id": self.id,
            "studio_id": self.studio_id,
            "name": self.name,
            "capacity": self.capacity,
            "description": self.description,
            "equipment": self.equipment,
            "floor": self.floor,
            "room_number": self.room_number,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

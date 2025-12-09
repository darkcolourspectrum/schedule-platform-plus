"""
Studio model - Студии вокальной школы
"""

from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.classroom import Classroom


class Studio(Base, TimestampMixin):
    """
    Модель студии вокальной школы
    
    Студия - это физическое местоположение школы (филиал)
    В одной студии может быть несколько кабинетов
    """
    
    __tablename__ = "studios"
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True)
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Название студии"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание студии"
    )
    
    # Контактная информация
    address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Адрес студии"
    )
    
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Телефон студии"
    )
    
    email: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Email студии"
    )
    
    # Статус
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Активна ли студия"
    )
    
    # Relationships
    classrooms: Mapped[List["Classroom"]] = relationship(
        "Classroom",
        back_populates="studio",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    def __repr__(self) -> str:
        return f"<Studio(id={self.id}, name='{self.name}', is_active={self.is_active})>"
    
    def to_dict(self) -> dict:
        """Конвертация в словарь"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "address": self.address,
            "phone": self.phone,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

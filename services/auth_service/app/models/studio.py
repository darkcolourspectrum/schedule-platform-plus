from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Boolean
from typing import List, TYPE_CHECKING

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Studio(Base, TimestampMixin):
    """Модель студии"""
    
    __tablename__ = "studios"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", 
        back_populates="studio",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Studio(id={self.id}, name='{self.name}')>"
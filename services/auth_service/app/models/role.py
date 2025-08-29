from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text
from typing import List, TYPE_CHECKING
from enum import Enum

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class RoleType(str, Enum):
    """Типы ролей в системе"""
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    GUEST = "guest"


class Role(Base, TimestampMixin):
    """Модель роли пользователя"""
    
    __tablename__ = "roles"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", 
        back_populates="role"
    )
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}')>"
"""
READ-ONLY модели из Auth Service
Используются ТОЛЬКО для чтения User данных
НЕ МОДИФИЦИРОВАТЬ через Schedule Service!
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Role(Base):
    """READ-ONLY модель Role из Auth Service"""
    
    __tablename__ = "roles"
    __table_args__ = {"schema": "public"}
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200))


class User(Base):
    """
    READ-ONLY модель User из Auth Service
    
    ВАЖНО: НЕ МОДИФИЦИРОВАТЬ через Schedule Service!
    Используется ТОЛЬКО для чтения данных пользователей
    """
    
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Роль и студия
    role_id: Mapped[int] = mapped_column(ForeignKey("public.roles.id"))
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Временные метки
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Relationship
    role: Mapped["Role"] = relationship("Role")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

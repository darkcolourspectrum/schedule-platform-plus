"""
READ-ONLY модели из Auth Service
Используются ТОЛЬКО для чтения User данных
НЕ МОДИФИЦИРОВАТЬ через Admin Service!
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Role(Base):
    """
    READ-ONLY модель Role из Auth Service
    """
    
    __tablename__ = "roles"
    __table_args__ = {"schema": "public"}
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200))


class User(Base):
    """
    READ-ONLY модель User из Auth Service
    
    ВАЖНО: НЕ МОДИФИЦИРОВАТЬ через Admin Service!
    Для изменения User используйте Auth Service API
    
    Эта модель используется ТОЛЬКО для:
    - Чтения данных пользователей
    - Кэширования в Redis
    - Отображения в админ-панели
    """
    
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}
    
    # Основные поля
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
    
    # Безопасность
    login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Временные метки
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Privacy policy
    privacy_policy_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    
    privacy_policy_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Relationships
    role: Mapped["Role"] = relationship("Role", foreign_keys=[role_id])
    
    @property
    def full_name(self) -> str:
        """Полное имя пользователя"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_admin(self) -> bool:
        """Проверка роли администратора"""
        return self.role and self.role.name == "admin"
    
    @property
    def is_teacher(self) -> bool:
        """Проверка роли преподавателя"""
        return self.role and self.role.name == "teacher"
    
    @property
    def is_student(self) -> bool:
        """Проверка роли ученика"""
        return self.role and self.role.name == "student"
    
    @property
    def is_locked(self) -> bool:
        """Проверка блокировки аккаунта"""
        if not self.locked_until:
            return False
        return datetime.utcnow() < self.locked_until
    
    def to_dict(self) -> dict:
        """Конвертация в словарь"""
        return {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "phone": self.phone,
            "role": {
                "id": self.role.id,
                "name": self.role.name,
                "description": self.role.description
            } if self.role else None,
            "studio_id": self.studio_id,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "is_locked": self.is_locked,
            "login_attempts": self.login_attempts,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "privacy_policy_accepted": self.privacy_policy_accepted
        }
    
    def __repr__(self) -> str:
        role_name = self.role.name if self.role else None
        return f"<User(id={self.id}, email='{self.email}', role='{role_name}')>"

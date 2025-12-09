from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text, Integer
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.refresh_token import RefreshToken


class User(Base, TimestampMixin):
    """Модель пользователя"""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Authentication
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # OAuth fields
    vk_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Privacy policy
    privacy_policy_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    privacy_policy_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Security
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Profile
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Foreign Keys
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Ссылка на студию (без FK constraint)
    
    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="select")
    # studio relationship УДАЛЁН - Studio модель перенесена в Admin Service
    # studio_id остаётся как обычное поле для хранения связи
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", 
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
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
    
    def __repr__(self) -> str:
        role_name = self.role.name if self.role else None
        return f"<User(id={self.id}, email='{self.email}', role='{role_name}')>"
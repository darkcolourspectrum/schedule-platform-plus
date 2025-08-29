from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, ForeignKey, Boolean, Text
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base, TimestampMixin):
    """Модель refresh токена"""
    
    __tablename__ = "refresh_tokens"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Device info for multi-device support
    device_info: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения срока действия токена"""
        return datetime.utcnow() >= self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Проверка валидности токена"""
        return not self.is_revoked and not self.is_expired
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class TokenBlacklist(Base, TimestampMixin):
    """Модель черного списка токенов"""
    
    __tablename__ = "token_blacklist"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    token_jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'access' or 'refresh'
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Optional: связь с пользователем для аудита
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 'logout', 'security', etc.
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения срока действия записи в blacklist"""
        return datetime.utcnow() >= self.expires_at
    
    def __repr__(self) -> str:
        return f"<TokenBlacklist(id={self.id}, jti='{self.token_jti}', type='{self.token_type}')>"
"""
Импорт всех моделей для правильной инициализации SQLAlchemy
"""

# Импортируем все модели в правильном порядке
from app.models.base import Base, TimestampMixin
from app.models.role import Role, RoleType
from app.models.studio import Studio
from app.models.user import User
from app.models.refresh_token import RefreshToken, TokenBlacklist

# Список всех моделей для экспорта
__all__ = [
    "Base",
    "TimestampMixin",
    "Role",
    "RoleType", 
    "Studio",
    "User",
    "RefreshToken",
    "TokenBlacklist"
]
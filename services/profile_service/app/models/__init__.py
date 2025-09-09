"""
Модели данных для Profile Service
"""

from app.models.base import Base, BaseModel, TimestampMixin
from app.models.profile import UserProfile
from app.models.comment import Comment, CommentType, CommentStatus
from app.models.activity import UserActivity, ActivityType, ActivityLevel

# Экспортируем все модели для автоматического обнаружения Alembic
__all__ = [
    # Базовые классы
    "Base",
    "BaseModel", 
    "TimestampMixin",
    
    # Основные модели
    "UserProfile",
    "Comment",
    "UserActivity",
    
    # Enums
    "CommentType",
    "CommentStatus", 
    "ActivityType",
    "ActivityLevel"
]
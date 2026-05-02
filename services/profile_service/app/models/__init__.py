"""
Модели данных для Profile Service
"""
from app.models.base import Base, BaseModel, TimestampMixin
from app.models.profile import UserProfile
from app.models.user_cache import UserCache
from app.models.processed_event import ProcessedEvent

# Экспортируем все модели для автоматического обнаружения Alembic
__all__ = [
    # Базовые классы
    "Base",
    "BaseModel", 
    "TimestampMixin",
    "UserCache",
    "ProcessedEvent",
    
    # Основные модели
    "UserProfile",
]
"""
Модели данных для Profile Service
"""
from app.models.base import Base, BaseModel, TimestampMixin
from app.models.profile import UserProfile

# Экспортируем все модели для автоматического обнаружения Alembic
__all__ = [
    # Базовые классы
    "Base",
    "BaseModel", 
    "TimestampMixin",
    
    # Основные модели
    "UserProfile",
]
"""
Модели данных для Schedule Service
Импорт всех моделей для правильной инициализации SQLAlchemy
"""

# Импортируем модели в правильном порядке (базовые -> зависимые)
from app.models.base import Base, TimestampMixin
from app.models.studio import Studio
from app.models.room import Room, RoomType
from app.models.time_slot import TimeSlot, SlotStatus
from app.models.lesson import Lesson, LessonStatus, LessonType

# Экспортируем все для использования в других модулях
__all__ = [
    # Базовые классы
    "Base",
    "TimestampMixin",
    
    # Основные модели
    "Studio",
    "Room",
    "TimeSlot", 
    "Lesson",
    
    # Enums
    "RoomType",
    "SlotStatus",
    "LessonStatus",
    "LessonType"
]
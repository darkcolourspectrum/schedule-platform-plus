"""
Базовые модели для Profile Service
Следует паттернам Auth Service и Schedule Service
"""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей Profile Service"""
    pass


class TimestampMixin:
    """Миксин для автоматического управления временными метками"""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
        comment="Время создания записи"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Время последнего обновления записи"
    )
    
    @property
    def created_at_str(self) -> str:
        """Строковое представление времени создания"""
        if self.created_at:
            return self.created_at.isoformat()
        return ""
    
    @property
    def updated_at_str(self) -> str:
        """Строковое представление времени обновления"""
        if self.updated_at:
            return self.updated_at.isoformat()
        return ""


class BaseModel(Base, TimestampMixin):
    """
    Базовая модель с ID и временными метками
    Используется как основа для всех основных моделей
    """
    __abstract__ = True
    
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Уникальный идентификатор записи"
    )
    
    def to_dict(self, exclude_fields: set = None) -> dict[str, Any]:
        """
        Преобразование модели в словарь
        
        Args:
            exclude_fields: Поля для исключения из результата
        
        Returns:
            dict: Словарь с данными модели
        """
        exclude_fields = exclude_fields or set()
        
        result = {}
        for column in self.__table__.columns:
            if column.name not in exclude_fields:
                value = getattr(self, column.name)
                
                # Обработка datetime объектов
                if isinstance(value, datetime):
                    result[column.name] = value.isoformat()
                else:
                    result[column.name] = value
        
        return result
    
    def update_from_dict(self, data: dict[str, Any], allowed_fields: set = None) -> None:
        """
        Обновление модели из словаря
        
        Args:
            data: Данные для обновления
            allowed_fields: Разрешенные для обновления поля
        """
        allowed_fields = allowed_fields or set()
        
        for key, value in data.items():
            if allowed_fields and key not in allowed_fields:
                continue
                
            if hasattr(self, key) and key != 'id':
                setattr(self, key, value)
    
    def __repr__(self) -> str:
        """Строковое представление модели"""
        return f"<{self.__class__.__name__}(id={self.id})>"
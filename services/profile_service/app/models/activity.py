"""
Модель истории активности пользователей для Profile Service
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, JSON, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import BaseModel


class ActivityType(str, enum.Enum):
    """Типы активности пользователей"""
    # Профиль
    PROFILE_CREATED = "profile_created"
    PROFILE_UPDATED = "profile_updated"
    AVATAR_UPLOADED = "avatar_uploaded"
    
    # Уроки
    LESSON_BOOKED = "lesson_booked"
    LESSON_CANCELLED = "lesson_cancelled"
    LESSON_COMPLETED = "lesson_completed"
    LESSON_MISSED = "lesson_missed"
    
    # Комментарии и отзывы
    COMMENT_CREATED = "comment_created"
    COMMENT_UPDATED = "comment_updated"
    REVIEW_LEFT = "review_left"
    
    # Аутентификация
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    
    # Настройки
    SETTINGS_UPDATED = "settings_updated"
    NOTIFICATIONS_UPDATED = "notifications_updated"
    
    # Административные действия
    USER_PROMOTED = "user_promoted"
    USER_DEMOTED = "user_demoted"
    ACCOUNT_SUSPENDED = "account_suspended"
    ACCOUNT_RESTORED = "account_restored"


class ActivityLevel(str, enum.Enum):
    """Уровни важности активности"""
    LOW = "low"           # Обычная активность
    MEDIUM = "medium"     # Важная активность
    HIGH = "high"         # Критичная активность
    SYSTEM = "system"     # Системная активность


class UserActivity(BaseModel):
    """
    Модель истории активности пользователей
    Логирует все важные действия для аналитики и безопасности
    """
    __tablename__ = "user_activities"
    
    # Пользователь
    user_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="ID пользователя (из Auth Service)"
    )
    
    # Тип и описание активности
    activity_type: Mapped[ActivityType] = mapped_column(
        Enum(ActivityType),
        nullable=False,
        index=True,
        comment="Тип активности"
    )
    
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Краткое описание активности"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Подробное описание активности"
    )
    
    level: Mapped[ActivityLevel] = mapped_column(
        Enum(ActivityLevel),
        default=ActivityLevel.LOW,
        nullable=False,
        index=True,
        comment="Уровень важности"
    )
    
    # Контекст активности
    target_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Тип объекта, с которым связана активность"
    )
    
    target_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="ID объекта"
    )
    
    # Метаданные активности - ИСПРАВЛЕНО!
    activity_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Дополнительные данные активности в JSON"
    )
    
    # Технические данные
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6 поддержка
        nullable=True,
        comment="IP адрес пользователя"
    )
    
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User-Agent браузера"
    )
    
    session_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="ID сессии"
    )
    
    # Дополнительные поля
    success: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Успешность операции"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке (если операция неуспешна)"
    )
    
    @property
    def is_important(self) -> bool:
        """Является ли активность важной"""
        return self.level in [ActivityLevel.HIGH, ActivityLevel.SYSTEM]
    
    @property
    def is_recent(self) -> bool:
        """Является ли активность недавней (менее 1 часа)"""
        if self.created_at:
            time_diff = datetime.now() - self.created_at
            return time_diff.total_seconds() < 3600
        return False
    
    @property
    def time_ago(self) -> str:
        """Человекочитаемое время активности"""
        if not self.created_at:
            return "неизвестно"
        
        now = datetime.now()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} дн. назад"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} ч. назад"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} мин. назад"
        else:
            return "только что"
    
    @classmethod
    def create_activity(
        cls,
        user_id: int,
        activity_type: ActivityType,
        title: str,
        description: Optional[str] = None,
        level: ActivityLevel = ActivityLevel.LOW,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        activity_data: Optional[dict] = None,  # ИСПРАВЛЕНО!
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> 'UserActivity':
        """
        Создание новой записи активности
        
        Args:
            user_id: ID пользователя
            activity_type: Тип активности
            title: Краткое описание
            description: Подробное описание
            level: Уровень важности
            target_type: Тип связанного объекта
            target_id: ID связанного объекта
            activity_data: Дополнительные данные
            ip_address: IP адрес
            user_agent: User-Agent
            session_id: ID сессии
            success: Успешность операции
            error_message: Сообщение об ошибке
        
        Returns:
            UserActivity: Новая запись активности
        """
        return cls(
            user_id=user_id,
            activity_type=activity_type,
            title=title,
            description=description,
            level=level,
            target_type=target_type,
            target_id=target_id,
            activity_metadata=activity_data or {},  # ИСПРАВЛЕНО!
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            success=success,
            error_message=error_message
        )
    
    def to_dict_public(self) -> dict:
        """Публичное представление активности (без технических данных)"""
        result = self.to_dict(exclude_fields={
            'ip_address',
            'user_agent', 
            'session_id',
            'error_message'
        })
        
        result['time_ago'] = self.time_ago
        result['is_important'] = self.is_important
        result['is_recent'] = self.is_recent
        
        return result
    
    def to_dict_admin(self) -> dict:
        """Административное представление активности (все данные)"""
        result = self.to_dict()
        result['time_ago'] = self.time_ago
        result['is_important'] = self.is_important
        result['is_recent'] = self.is_recent
        return result
    
    def __repr__(self) -> str:
        return f"<UserActivity(user_id={self.user_id}, type={self.activity_type}, success={self.success})>"
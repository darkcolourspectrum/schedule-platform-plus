"""
Модель профиля пользователя для Profile Service
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class UserProfile(BaseModel):
    """
    Расширенный профиль пользователя
    Дополняет базовую информацию из Auth Service
    """
    __tablename__ = "user_profiles"
    
    # Связь с пользователем из Auth Service
    user_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="ID пользователя из Auth Service"
    )
    
    # Основная информация профиля
    display_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Отображаемое имя пользователя"
    )
    
    bio: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Биография пользователя"
    )
    
    avatar_filename: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Имя файла аватара"
    )
    
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Номер телефона"
    )
    
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата рождения"
    )
    
    # Настройки профиля
    is_profile_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Публичность профиля"
    )
    
    show_contact_info: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Показывать контактную информацию"
    )
    
    # Настройки уведомлений
    notification_preferences: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "email_lessons": True,
            "email_reminders": True,
            "email_comments": True,
            "push_lessons": True,
            "push_reminders": True,
            "push_comments": False
        },
        nullable=False,
        comment="Настройки уведомлений в JSON формате"
    )
    
    # Дополнительные настройки профиля
    profile_settings: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "timezone": "Europe/Moscow",
            "language": "ru",
            "theme": "light",
            "dashboard_layout": "default"
        },
        nullable=False,
        comment="Настройки профиля в JSON формате"
    )
    
    # Статистика профиля
    profile_views: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество просмотров профиля"
    )
    
    last_activity: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последней активности"
    )
    
    # Специфичные поля для ролей
    
    # Для студентов
    student_info: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Дополнительная информация о студенте"
    )
    
    # Для преподавателей
    teacher_info: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Дополнительная информация о преподавателе"
    )
    
    @property
    def avatar_url(self) -> Optional[str]:
        """URL аватара пользователя"""
        if self.avatar_filename:
            from app.config import settings
            return settings.get_avatar_url(self.avatar_filename)
        return None
    
    @property
    def age(self) -> Optional[int]:
        """Возраст пользователя"""
        if self.date_of_birth:
            today = datetime.now(self.date_of_birth.tzinfo)
            return (today - self.date_of_birth).days // 365
        return None
    
    def get_notification_setting(self, key: str) -> bool:
        """Получение настройки уведомлений"""
        return self.notification_preferences.get(key, False)
    
    def update_notification_setting(self, key: str, value: bool) -> None:
        """Обновление настройки уведомлений"""
        if self.notification_preferences is None:
            self.notification_preferences = {}
        
        self.notification_preferences[key] = value
    
    def get_profile_setting(self, key: str, default=None):
        """Получение настройки профиля"""
        return self.profile_settings.get(key, default)
    
    def update_profile_setting(self, key: str, value) -> None:
        """Обновление настройки профиля"""
        if self.profile_settings is None:
            self.profile_settings = {}
        
        self.profile_settings[key] = value
    
    def increment_views(self) -> None:
        """Увеличение счетчика просмотров профиля"""
        self.profile_views += 1
    
    def update_last_activity(self) -> None:
        """Обновление времени последней активности"""
        self.last_activity = datetime.now()
    
    def to_dict_public(self) -> dict:
        """Публичное представление профиля (без приватных данных)"""
        result = self.to_dict(exclude_fields={
            'notification_preferences', 
            'profile_settings',
            'phone'
        })
        
        # Добавляем вычисляемые поля
        result['avatar_url'] = self.avatar_url
        result['age'] = self.age
        
        # Фильтруем приватные данные в зависимости от настроек
        if not self.show_contact_info:
            result.pop('phone', None)
        
        return result
    
    def to_dict_private(self) -> dict:
        """Приватное представление профиля (все данные для владельца)"""
        result = self.to_dict()
        result['avatar_url'] = self.avatar_url
        result['age'] = self.age
        return result
    
    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id}, display_name='{self.display_name}')>"
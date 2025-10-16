"""
Pydantic схемы для профилей пользователей
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, EmailStr, validator


class ProfileBase(BaseModel):
    """Базовая схема профиля"""
    display_name: Optional[str] = Field(None, max_length=100, description="Отображаемое имя")
    bio: Optional[str] = Field(None, max_length=1000, description="Биография")
    phone: Optional[str] = Field(None, max_length=20, description="Номер телефона")
    date_of_birth: Optional[date] = Field(None, description="Дата рождения")
    is_profile_public: bool = Field(True, description="Публичность профиля")
    show_contact_info: bool = Field(False, description="Показывать контактную информацию")


class ProfileCreate(ProfileBase):
    """Схема для создания профиля"""
    pass


class ProfileUpdate(BaseModel):
    """Схема для обновления профиля"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Имя")
    last_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Фамилия")
    display_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    phone: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    is_profile_public: Optional[bool] = None
    show_contact_info: Optional[bool] = None


class NotificationPreferences(BaseModel):
    """Схема настроек уведомлений"""
    email_lessons: bool = Field(True, description="Уведомления о уроках на email")
    email_reminders: bool = Field(True, description="Напоминания на email")
    email_comments: bool = Field(True, description="Уведомления о комментариях на email")
    push_lessons: bool = Field(True, description="Push-уведомления о уроках")
    push_reminders: bool = Field(True, description="Push-напоминания")
    push_comments: bool = Field(False, description="Push-уведомления о комментариях")


class ProfileSettings(BaseModel):
    """Схема настроек профиля"""
    timezone: str = Field("Europe/Moscow", description="Часовой пояс")
    language: str = Field("ru", description="Язык интерфейса")
    theme: str = Field("light", description="Тема оформления")
    dashboard_layout: str = Field("default", description="Макет дашборда")


class UserInfo(BaseModel):
    """Схема базовой информации о пользователе из Auth Service"""
    id: int = Field(..., description="ID пользователя")
    email: EmailStr = Field(..., description="Email пользователя")
    first_name: Optional[str] = Field(None, description="Имя")
    last_name: Optional[str] = Field(None, description="Фамилия")
    role: Dict[str, Any] = Field(..., description="Роль пользователя")
    is_verified: bool = Field(False, description="Верифицирован ли пользователь")
    created_at: Optional[datetime] = Field(None, description="Дата создания аккаунта")


class ProfileResponse(BaseModel):
    """Схема ответа с профилем пользователя"""
    # Данные из Auth Service
    user_info: UserInfo
    
    # Данные из Profile Service
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    
    # Настройки
    is_profile_public: bool = True
    show_contact_info: bool = False
    notification_preferences: NotificationPreferences
    profile_settings: ProfileSettings
    
    # Статистика
    profile_views: int = 0
    last_activity: Optional[datetime] = None
    
    # Дополнительная информация по ролям
    student_info: Optional[Dict[str, Any]] = None
    teacher_info: Optional[Dict[str, Any]] = None
    
    # Временные метки
    created_at: datetime
    updated_at: datetime
    
    @validator('notification_preferences', pre=True)
    def parse_notification_preferences(cls, v):
        """Парсим настройки уведомлений из JSON"""
        if isinstance(v, dict):
            return NotificationPreferences(**v)
        return v
    
    @validator('profile_settings', pre=True)
    def parse_profile_settings(cls, v):
        """Парсим настройки профиля из JSON"""
        if isinstance(v, dict):
            return ProfileSettings(**v)
        return v


class ProfilePublicResponse(BaseModel):
    """Схема публичного профиля (для других пользователей)"""
    user_id: int
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    age: Optional[int] = None
    role: str
    is_verified: bool = False
    profile_views: int = 0
    last_activity: Optional[datetime] = None
    created_at: datetime


class ProfileSearchResult(BaseModel):
    """Схема результата поиска профилей"""
    user_id: int
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    role: str
    is_verified: bool = False
    profile_views: int = 0


class ProfileListResponse(BaseModel):
    """Схема списка профилей с пагинацией"""
    profiles: List[ProfileSearchResult]
    total: int
    limit: int
    offset: int
    has_more: bool


class AvatarUploadResponse(BaseModel):
    """Схема ответа на загрузку аватара"""
    success: bool
    filename: Optional[str] = None
    url: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None


class AvatarInfo(BaseModel):
    """Схема информации об аватаре"""
    filename: str
    url: str
    size_bytes: int
    width: int
    height: int
    format: str
    created_at: float
    modified_at: float


class StudentInfo(BaseModel):
    """Дополнительная информация о студенте"""
    preferred_time: Optional[str] = Field(None, description="Предпочитаемое время занятий")
    skill_level: Optional[str] = Field(None, description="Уровень навыков")
    goals: Optional[str] = Field(None, description="Цели обучения")
    notes: Optional[str] = Field(None, description="Дополнительные заметки")


class TeacherInfo(BaseModel):
    """Дополнительная информация о преподавателе"""
    specializations: List[str] = Field(default_factory=list, description="Специализации")
    experience_years: Optional[int] = Field(None, description="Опыт работы в годах")
    education: Optional[str] = Field(None, description="Образование")
    achievements: Optional[str] = Field(None, description="Достижения")
    teaching_style: Optional[str] = Field(None, description="Стиль преподавания")
    available_hours: Optional[Dict[str, Any]] = Field(None, description="Доступные часы")


class ProfileStatsResponse(BaseModel):
    """Схема статистики профиля"""
    profile_views: int
    total_comments: int
    recent_activities_count: int
    
    # Для студентов
    total_lessons: Optional[int] = None
    completed_lessons: Optional[int] = None
    
    # Для преподавателей
    total_students: Optional[int] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None


class MessageResponse(BaseModel):
    """Схема ответа с сообщением"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Схема ответа с ошибкой"""
    error: str
    detail: Optional[str] = None
    success: bool = False
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
    first_name: Optional[str] = Field(None, max_length=100, description="Имя")
    last_name: Optional[str] = Field(None, max_length=100, description="Фамилия")
    display_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
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
    
    # Вычисляемые поля
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ProfilePublicResponse(BaseModel):
    """Публичная схема профиля (для других пользователей)"""
    user_info: UserInfo
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # Контактная информация только если разрешено
    email: Optional[str] = None
    phone: Optional[str] = None
    
    # Публичная статистика
    profile_views: int = 0
    
    # Дополнительная информация по ролям (только публичная)
    student_info: Optional[Dict[str, Any]] = None
    teacher_info: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class ProfileSearchResult(BaseModel):
    """Схема результата поиска профилей"""
    profiles: List[ProfilePublicResponse]
    total: int
    page: int
    size: int
    pages: int


class ProfileListResponse(BaseModel):
    """Схема ответа со списком профилей"""
    profiles: List[ProfilePublicResponse]
    total: int
    page: int
    size: int
    pages: int


class AvatarUploadResponse(BaseModel):
    """Схема ответа на загрузку аватара"""
    success: bool
    filename: str
    url: str
    size: int


class AvatarInfo(BaseModel):
    """Схема информации об аватаре"""
    filename: str
    url: str
    size: int
    mime_type: str
    uploaded_at: datetime


class StudentInfo(BaseModel):
    """Дополнительная информация о студенте"""
    level: Optional[str] = None
    goals: Optional[List[str]] = None
    preferences: Optional[Dict[str, Any]] = None
    learning_style: Optional[str] = None


class TeacherInfo(BaseModel):
    """Дополнительная информация о преподавателе"""
    subjects: Optional[List[str]] = None
    experience_years: Optional[int] = None
    education: Optional[List[str]] = None
    certificates: Optional[List[str]] = None
    teaching_style: Optional[str] = None
    hourly_rate: Optional[float] = None


class ProfileStatsResponse(BaseModel):
    """Схема статистики профилей"""
    total_profiles: int
    active_profiles: int
    verified_profiles: int
    public_profiles: int
    students_count: int
    teachers_count: int
    recent_registrations: int


class MessageResponse(BaseModel):
    """Схема ответа с сообщением"""
    message: str


class ErrorResponse(BaseModel):
    """Схема ответа с ошибкой"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
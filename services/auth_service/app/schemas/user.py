from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Базовая схема пользователя"""
    
    email: EmailStr = Field(..., description="Email пользователя")
    first_name: str = Field(..., min_length=1, max_length=100, description="Имя")
    last_name: str = Field(..., min_length=1, max_length=100, description="Фамилия")
    phone: Optional[str] = Field(None, max_length=20, description="Телефон")


class UserCreate(UserBase):
    """Схема для создания пользователя"""
    
    password: str = Field(..., min_length=8, description="Пароль")
    role_id: int = Field(..., description="ID роли")
    studio_id: Optional[int] = Field(None, description="ID студии")
    privacy_policy_accepted: bool = Field(True, description="Согласие на обработку данных")


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""
    
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    bio: Optional[str] = Field(None, description="Биография")
    avatar_url: Optional[str] = Field(None, description="URL аватара")


class UserProfile(BaseModel):
    """Схема профиля пользователя"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    role: str
    studio_id: Optional[int]
    studio_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """Схема элемента списка пользователей"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    studio_name: Optional[str]
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class CurrentUser(BaseModel):
    """Схема текущего авторизованного пользователя"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    studio_id: Optional[int]
    studio_name: Optional[str]
    is_admin: bool
    is_teacher: bool
    is_student: bool
    permissions: list[str] = Field(default_factory=list)
    
    class Config:
        from_attributes = True
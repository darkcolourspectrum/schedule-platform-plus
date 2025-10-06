from pydantic import BaseModel, EmailStr, Field, field_validator, model_serializer
from typing import Optional, Any
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
    phone: Optional[str] = None
    role: str
    studio_id: Optional[int] = None
    studio_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    @classmethod
    def from_orm(cls, user: Any) -> 'UserProfile':
        """
        Создает UserProfile из ORM объекта User
        
        ИСПРАВЛЕНО: Правильно обрабатывает relationship поля role и studio
        """
        return cls(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            role=user.role.name if hasattr(user, 'role') and user.role else 'student',
            studio_id=user.studio_id,
            studio_name=user.studio.name if hasattr(user, 'studio') and user.studio else None,
            bio=user.bio if hasattr(user, 'bio') else None,
            avatar_url=user.avatar_url if hasattr(user, 'avatar_url') else None,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            last_login=user.last_login
        )
    
    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """Схема элемента списка пользователей"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    studio_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    @classmethod
    def from_orm(cls, user: Any) -> 'UserListItem':
        """Создает UserListItem из ORM объекта User"""
        return cls(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role.name if hasattr(user, 'role') and user.role else 'student',
            studio_name=user.studio.name if hasattr(user, 'studio') and user.studio else None,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
    
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
    studio_id: Optional[int] = None
    studio_name: Optional[str] = None
    is_admin: bool
    is_teacher: bool
    is_student: bool
    permissions: list[str] = Field(default_factory=list)
    
    class Config:
        from_attributes = True
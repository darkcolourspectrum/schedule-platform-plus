from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.models.role import RoleType


class AssignTeacherRequest(BaseModel):
    """Схема для назначения роли преподавателя"""
    
    user_id: int = Field(..., description="ID пользователя")
    studio_id: int = Field(..., description="ID студии")


class UserRoleUpdate(BaseModel):
    """Схема для изменения роли пользователя"""
    
    user_id: int = Field(..., description="ID пользователя")
    role: RoleType = Field(..., description="Новая роль")


class StudioAssignmentRequest(BaseModel):
    """Схема для привязки к студии"""
    
    user_id: int = Field(..., description="ID пользователя")
    studio_id: int = Field(..., description="ID студии")


class AdminUserResponse(BaseModel):
    """Расширенная схема пользователя для админ-панели"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str]
    role: str
    studio_id: Optional[int]
    studio_name: Optional[str]
    is_active: bool
    is_verified: bool
    login_attempts: int
    locked_until: Optional[datetime]
    last_login: Optional[datetime]
    created_at: datetime
    privacy_policy_accepted: bool
    privacy_policy_accepted_at: Optional[datetime]
    
    @classmethod
    def from_user(cls, user):
        """Создание из модели User"""
        return cls(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            phone=user.phone,
            role=user.role.name if user.role else "unknown",
            studio_id=user.studio_id,
            studio_name=user.studio.name if user.studio else None,
            is_active=user.is_active,
            is_verified=user.is_verified,
            login_attempts=user.login_attempts,
            locked_until=user.locked_until,
            last_login=user.last_login,
            created_at=user.created_at,
            privacy_policy_accepted=user.privacy_policy_accepted,
            privacy_policy_accepted_at=user.privacy_policy_accepted_at
        )


class TeacherCandidate(BaseModel):
    """Кандидат на роль преподавателя"""
    
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class StudioCreate(BaseModel):
    """Схема для создания студии"""
    
    name: str = Field(..., min_length=1, max_length=255, description="Название студии")
    description: Optional[str] = Field(None, description="Описание студии")
    address: Optional[str] = Field(None, max_length=500, description="Адрес")
    phone: Optional[str] = Field(None, max_length=20, description="Телефон")
    email: Optional[str] = Field(None, max_length=255, description="Email")


class StudioUpdate(BaseModel):
    """Схема для обновления студии"""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = Field(None)


class StudioInfo(BaseModel):
    """Информация о студии для админ-панели"""
    
    id: int
    name: str
    description: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    teachers_count: int = 0
    students_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True
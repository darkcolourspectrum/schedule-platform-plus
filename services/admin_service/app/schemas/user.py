"""User schemas"""
from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


class RoleInfo(BaseModel):
    """Role information"""
    id: int
    name: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None


class UserResponse(BaseModel):
    """User response schema - базовая"""
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role_id: int
    studio_id: Optional[int] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserDetailResponse(BaseModel):
    """User detail response - ПОЛНАЯ схема для фронта"""
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str  # ← Добавлено
    phone: Optional[str] = None
    role_id: int
    role: str  # ← Добавлено (название роли)
    studio_id: Optional[int] = None
    studio_name: Optional[str] = None  # ← Добавлено
    is_active: bool
    is_verified: bool
    login_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    privacy_policy_accepted: bool
    privacy_policy_accepted_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """User update request"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class UserRoleUpdateRequest(BaseModel):
    """User role update request"""
    role: str  # admin, teacher, student


class UserStudioAssignRequest(BaseModel):
    """User studio assignment request"""
    studio_id: int
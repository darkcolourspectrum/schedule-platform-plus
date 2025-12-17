"""
Общие schemas
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    """Стандартный ответ об успехе"""
    
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    """Стандартный ответ об ошибке"""
    
    success: bool = False
    error: str
    details: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Ответ health check"""
    
    status: str
    service: str
    version: str
    database: bool
    auth_database: bool
    redis: bool


class PaginationParams(BaseModel):
    """Параметры пагинации"""
    
    limit: int = Field(50, ge=1, le=100, description="Количество элементов")
    offset: int = Field(0, ge=0, description="Смещение")


class UserInfo(BaseModel):
    """Информация о пользователе"""
    
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    studio_id: Optional[int] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class StudioInfo(BaseModel):
    """Информация о студии"""
    
    id: int
    name: str
    address: Optional[str] = None
    is_active: bool


class ClassroomInfo(BaseModel):
    """Информация о кабинете"""
    
    id: int
    studio_id: int
    name: str
    capacity: Optional[int] = None
    is_active: bool

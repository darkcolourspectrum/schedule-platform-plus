from pydantic import BaseModel, Field
from typing import Optional


class RoleBase(BaseModel):
    """Базовая схема роли"""
    
    name: str = Field(..., min_length=1, max_length=50, description="Название роли")
    description: Optional[str] = Field(None, description="Описание роли")


class RoleCreate(RoleBase):
    """Схема для создания роли"""
    pass


class RoleUpdate(BaseModel):
    """Схема для обновления роли"""
    
    description: Optional[str] = Field(None, description="Описание роли")


class RoleResponse(RoleBase):
    """Схема ответа с данными роли"""
    
    id: int = Field(..., description="ID роли")
    
    class Config:
        from_attributes = True
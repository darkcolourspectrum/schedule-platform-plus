"""Studio Schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class StudioBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class StudioCreate(StudioBase):
    pass

class StudioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None

class StudioResponse(StudioBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    classrooms_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

"""Classroom Schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ClassroomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(1, ge=1, le=100)
    description: Optional[str] = None
    equipment: Optional[str] = None
    floor: Optional[int] = None
    room_number: Optional[str] = None

class ClassroomCreate(ClassroomBase):
    pass

class ClassroomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    equipment: Optional[str] = None
    floor: Optional[int] = None
    room_number: Optional[str] = None
    is_active: Optional[bool] = None

class ClassroomResponse(ClassroomBase):
    id: int
    studio_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

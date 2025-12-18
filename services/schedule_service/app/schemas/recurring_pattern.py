"""
Pydantic schemas для Recurring Patterns
"""

from typing import Optional, List
from datetime import date, time, datetime
from pydantic import BaseModel, Field, field_validator


class RecurringPatternCreate(BaseModel):
    """Схема создания шаблона повторяющегося занятия"""
    
    studio_id: int = Field(..., description="ID студии")
    teacher_id: int = Field(..., description="ID преподавателя")
    classroom_id: Optional[int] = Field(None, description="ID кабинета (NULL для онлайн)")
    
    day_of_week: int = Field(..., ge=1, le=7, description="День недели: 1=Пн, 2=Вт, ..., 7=Вс")
    start_time: time = Field(..., description="Время начала занятия")
    duration_minutes: int = Field(60, ge=30, le=180, description="Длительность в минутах")
    
    valid_from: date = Field(..., description="С какой даты начинает действовать")
    valid_until: Optional[date] = Field(None, description="До какой даты (NULL = бессрочно)")
    
    student_ids: List[int] = Field(default_factory=list, description="Список ID учеников")
    notes: Optional[str] = Field(None, max_length=1000, description="Заметки")
    
    @field_validator('valid_until')
    def validate_dates(cls, v, info):
        if v and info.data.get('valid_from') and v < info.data['valid_from']:
            raise ValueError('valid_until must be after valid_from')
        return v


class RecurringPatternUpdate(BaseModel):
    """Схема обновления шаблона"""
    
    classroom_id: Optional[int] = None
    start_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=30, le=180)
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=1000)
    student_ids: Optional[List[int]] = None


class RecurringPatternResponse(BaseModel):
    """Схема ответа с шаблоном"""
    
    id: int
    studio_id: int
    teacher_id: int
    classroom_id: Optional[int]
    
    day_of_week: int
    start_time: time
    duration_minutes: int
    
    valid_from: date
    valid_until: Optional[date]
    is_active: bool
    
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    # Дополнительные поля
    student_ids: List[int] = Field(default_factory=list)
    generated_lessons_count: int = Field(0, description="Количество сгенерированных занятий")
    
    model_config = {"from_attributes": True}


class RecurringPatternListResponse(BaseModel):
    """Схема списка шаблонов"""
    
    patterns: List[RecurringPatternResponse]
    total: int

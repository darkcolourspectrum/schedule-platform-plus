"""
Pydantic schemas для Lessons
"""

from typing import Optional, List
from datetime import date, time
from pydantic import BaseModel, Field, field_validator


class LessonCreate(BaseModel):
    """Схема создания разового занятия"""
    
    studio_id: int = Field(..., description="ID студии")
    teacher_id: int = Field(..., description="ID преподавателя")
    classroom_id: Optional[int] = Field(None, description="ID кабинета (NULL для онлайн)")
    
    lesson_date: date = Field(..., description="Дата занятия")
    start_time: time = Field(..., description="Время начала")
    duration_minutes: int = Field(60, ge=30, le=180, description="Длительность в минутах")
    
    student_ids: List[int] = Field(default_factory=list, description="Список ID учеников")
    notes: Optional[str] = Field(None, max_length=1000, description="Заметки")


class LessonUpdate(BaseModel):
    """Схема обновления занятия"""
    
    classroom_id: Optional[int] = None
    start_time: Optional[time] = None
    status: Optional[str] = Field(None, pattern="^(scheduled|completed|cancelled|missed)$")
    notes: Optional[str] = Field(None, max_length=1000)
    cancellation_reason: Optional[str] = Field(None, max_length=500)


class LessonStudentInfo(BaseModel):
    """Информация об ученике на занятии"""
    
    student_id: int
    attendance_status: str
    
    model_config = {"from_attributes": True}


class LessonResponse(BaseModel):
    """Схема ответа с занятием"""
    
    id: int
    studio_id: int
    teacher_id: int
    classroom_id: Optional[int]
    recurring_pattern_id: Optional[int]
    
    lesson_date: date
    start_time: time
    end_time: time
    status: str
    
    notes: Optional[str]
    cancellation_reason: Optional[str]
    created_at: str
    updated_at: str
    
    # Дополнительные поля
    students: List[LessonStudentInfo] = Field(default_factory=list)
    is_recurring: bool = Field(False, description="Создано из шаблона")
    
    model_config = {"from_attributes": True}


class LessonListResponse(BaseModel):
    """Схема списка занятий"""
    
    lessons: List[LessonResponse]
    total: int


class LessonWithDetails(LessonResponse):
    """Расширенная информация о занятии"""
    
    teacher_name: Optional[str] = None
    student_names: List[str] = Field(default_factory=list)
    classroom_name: Optional[str] = None
    studio_name: Optional[str] = None

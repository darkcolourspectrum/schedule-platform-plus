"""
Pydantic schemas для Schedule (расписание)
"""

from typing import Optional, List, Dict, Any
from datetime import date, time
from pydantic import BaseModel, Field


class ScheduleFilters(BaseModel):
    """Фильтры для получения расписания"""
    
    from_date: date = Field(..., description="Начальная дата")
    to_date: date = Field(..., description="Конечная дата")
    teacher_id: Optional[int] = Field(None, description="Фильтр по преподавателю")
    classroom_id: Optional[int] = Field(None, description="Фильтр по кабинету")
    status: Optional[str] = Field(None, description="Фильтр по статусу")


class ScheduleLessonItem(BaseModel):
    """Элемент расписания (упрощенная информация)"""
    
    lesson_id: int
    lesson_date: date
    start_time: time
    end_time: time
    status: str
    
    teacher_id: int
    teacher_name: str
    
    classroom_id: Optional[int]
    classroom_name: Optional[str]
    
    student_ids: List[int] = Field(default_factory=list)
    student_names: List[str] = Field(default_factory=list)
    
    is_recurring: bool
    notes: Optional[str] = None


class DaySchedule(BaseModel):
    """Расписание на один день"""
    
    date: date
    lessons: List[ScheduleLessonItem] = Field(default_factory=list)
    total_lessons: int = 0


class WeekSchedule(BaseModel):
    """Расписание на неделю"""
    
    week_start: date
    week_end: date
    days: List[DaySchedule] = Field(default_factory=list)
    total_lessons: int = 0


class StudioScheduleResponse(BaseModel):
    """Расписание студии"""
    
    studio_id: int
    studio_name: Optional[str] = None
    from_date: date
    to_date: date
    lessons: List[ScheduleLessonItem] = Field(default_factory=list)
    total: int = 0


class TeacherScheduleResponse(BaseModel):
    """Расписание преподавателя"""
    
    teacher_id: int
    teacher_name: Optional[str] = None
    from_date: date
    to_date: date
    lessons: List[ScheduleLessonItem] = Field(default_factory=list)
    total: int = 0


class StudentScheduleResponse(BaseModel):
    """Расписание ученика (его занятия)"""
    
    student_id: int
    student_name: Optional[str] = None
    from_date: date
    to_date: date
    lessons: List[ScheduleLessonItem] = Field(default_factory=list)
    total: int = 0


class GenerateLessonsRequest(BaseModel):
    """Запрос на генерацию занятий"""
    
    pattern_id: Optional[int] = Field(None, description="ID шаблона (если не указан - генерация для всех)")
    until_date: Optional[date] = Field(None, description="До какой даты генерировать")


class GenerateLessonsResponse(BaseModel):
    """Результат генерации занятий"""
    
    success: bool
    generated_count: int
    skipped_count: int = 0
    errors: List[str] = Field(default_factory=list)
    message: str


class ConflictCheckRequest(BaseModel):
    """Запрос проверки конфликтов"""
    
    classroom_id: int
    lesson_date: date
    start_time: time
    end_time: time
    exclude_lesson_id: Optional[int] = None


class ConflictCheckResponse(BaseModel):
    """Результат проверки конфликтов"""
    
    has_conflict: bool
    conflicting_lessons: List[Dict[str, Any]] = Field(default_factory=list)

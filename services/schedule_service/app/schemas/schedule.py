from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from enum import Enum

from app.models.lesson import LessonStatus, LessonType
from app.models.time_slot import SlotStatus
from app.models.room import RoomType


# === Базовые схемы ===

class StudioInfo(BaseModel):
    """Информация о студии"""
    id: int
    name: str
    working_hours: str
    
    class Config:
        from_attributes = True


class RoomInfo(BaseModel):
    """Информация о кабинете"""
    id: int
    name: str
    type: RoomType
    capacity: int
    equipment: str
    
    class Config:
        from_attributes = True


class TimeSlotInfo(BaseModel):
    """Информация о временном слоте"""
    id: int
    date: date
    time_range: str
    duration_minutes: int
    status: SlotStatus
    studio_name: str
    room_name: str
    has_lesson: bool = False
    reserved_by: Optional[str] = None
    
    class Config:
        from_attributes = True


class LessonInfo(BaseModel):
    """Информация об уроке"""
    id: int
    title: str
    type: LessonType
    status: LessonStatus
    date: str
    time_range: str
    teacher_name: str
    studio_name: str
    room_name: str
    students_count: int
    students_names: List[str]
    is_group: bool
    max_students: int
    
    class Config:
        from_attributes = True


class StudentInfo(BaseModel):
    """Информация об ученике в уроке"""
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    level: str = "beginner"
    enrolled_at: str


# === Схемы расписания ===

class ScheduleDay(BaseModel):
    """Расписание на один день"""
    date: str
    slots: List[Dict[str, Any]] = []
    lessons: List[Dict[str, Any]] = []


class TeacherSchedule(BaseModel):
    """Расписание преподавателя"""
    teacher_id: int
    period: Dict[str, str]
    schedule: List[ScheduleDay]


class StudentSchedule(BaseModel):
    """Расписание ученика"""
    student_id: int
    period: Dict[str, str]
    schedule: List[ScheduleDay]


class StudioSchedule(BaseModel):
    """Расписание студии"""
    studio: StudioInfo
    date: str
    rooms: List[Dict[str, Any]]


class AvailableSlot(BaseModel):
    """Доступный слот для бронирования"""
    slot_id: int
    date: str
    time_range: str
    duration_minutes: int
    studio_name: str
    room: RoomInfo


class AvailableSlotsResponse(BaseModel):
    """Ответ со списком доступных слотов"""
    studio_id: int
    period: Dict[str, str]
    total_slots: int
    available_slots: List[AvailableSlot]


# === Схемы для статистики ===

class LessonStatistics(BaseModel):
    """Статистика по урокам"""
    total_lessons: int
    by_status: Dict[str, int]
    by_type: Dict[str, int]
    period: Dict[str, Optional[str]]


class RoomUtilization(BaseModel):
    """Загруженность кабинета"""
    total_slots: int
    booked_slots: int
    reserved_slots: int
    available_slots: int
    utilization_percentage: float


class StudioUtilization(BaseModel):
    """Загруженность студии"""
    studio_id: int
    period: Dict[str, Any]
    overall: Dict[str, Any]
    by_room: Dict[str, RoomUtilization]


# === Ответы API ===

class MessageResponse(BaseModel):
    """Стандартный ответ с сообщением"""
    message: str


class SlotReservationResponse(BaseModel):
    """Ответ на резервирование слота"""
    message: str
    slot: TimeSlotInfo


class LessonCreatedResponse(BaseModel):
    """Ответ на создание урока"""
    message: str
    lesson: LessonInfo


class SlotGenerationResponse(BaseModel):
    """Ответ на генерацию слотов"""
    message: str
    studio_id: int
    week_start: str
    total_slots: int
    slots_per_day: int
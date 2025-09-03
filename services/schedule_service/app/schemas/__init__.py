"""
Pydantic схемы для Schedule Service
"""

from app.schemas.schedule import (
    StudioInfo,
    RoomInfo,
    TimeSlotInfo,
    LessonInfo,
    StudentInfo,
    ScheduleDay,
    TeacherSchedule,
    StudentSchedule,
    StudioSchedule,
    AvailableSlot,
    AvailableSlotsResponse,
    LessonStatistics,
    RoomUtilization,
    StudioUtilization,
    MessageResponse,
    SlotReservationResponse,
    LessonCreatedResponse,
    SlotGenerationResponse
)

__all__ = [
    "StudioInfo",
    "RoomInfo", 
    "TimeSlotInfo",
    "LessonInfo",
    "StudentInfo",
    "ScheduleDay",
    "TeacherSchedule",
    "StudentSchedule",
    "StudioSchedule",
    "AvailableSlot",
    "AvailableSlotsResponse",
    "LessonStatistics",
    "RoomUtilization",
    "StudioUtilization",
    "MessageResponse",
    "SlotReservationResponse",
    "LessonCreatedResponse",
    "SlotGenerationResponse"
]
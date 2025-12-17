"""Schemas package initialization"""

from app.schemas.recurring_pattern import (
    RecurringPatternCreate,
    RecurringPatternUpdate,
    RecurringPatternResponse,
    RecurringPatternListResponse
)
from app.schemas.lesson import (
    LessonCreate,
    LessonUpdate,
    LessonResponse,
    LessonListResponse,
    LessonWithDetails,
    LessonStudentInfo
)
from app.schemas.schedule import (
    ScheduleFilters,
    ScheduleLessonItem,
    DaySchedule,
    WeekSchedule,
    StudioScheduleResponse,
    TeacherScheduleResponse,
    StudentScheduleResponse,
    GenerateLessonsRequest,
    GenerateLessonsResponse,
    ConflictCheckRequest,
    ConflictCheckResponse
)
from app.schemas.common import (
    SuccessResponse,
    ErrorResponse,
    HealthCheckResponse,
    PaginationParams,
    UserInfo,
    StudioInfo,
    ClassroomInfo
)

__all__ = [
    "RecurringPatternCreate",
    "RecurringPatternUpdate",
    "RecurringPatternResponse",
    "RecurringPatternListResponse",
    "LessonCreate",
    "LessonUpdate",
    "LessonResponse",
    "LessonListResponse",
    "LessonWithDetails",
    "LessonStudentInfo",
    "ScheduleFilters",
    "ScheduleLessonItem",
    "DaySchedule",
    "WeekSchedule",
    "StudioScheduleResponse",
    "TeacherScheduleResponse",
    "StudentScheduleResponse",
    "GenerateLessonsRequest",
    "GenerateLessonsResponse",
    "ConflictCheckRequest",
    "ConflictCheckResponse",
    "SuccessResponse",
    "ErrorResponse",
    "HealthCheckResponse",
    "PaginationParams",
    "UserInfo",
    "StudioInfo",
    "ClassroomInfo",
]

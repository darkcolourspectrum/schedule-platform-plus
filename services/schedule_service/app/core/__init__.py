"""Core package initialization"""

from app.core.security import extract_role_name, verify_internal_api_key
from app.core.exceptions import (
    ScheduleServiceException,
    RecurringPatternNotFoundException,
    LessonNotFoundException,
    ClassroomConflictException,
    TeacherConflictException,
    StudentConflictException,
    DuplicateLessonException,
    InvalidTimeRangeException,
    InvalidLessonStatusException,
    PermissionDeniedException,
    StudioNotFoundException,
    ClassroomNotFoundException,
    UserNotFoundException,
    GenerationException,
    LessonImmutableException,
)

__all__ = [
    "extract_role_name",
    "verify_internal_api_key",
    "ScheduleServiceException",
    "RecurringPatternNotFoundException",
    "LessonNotFoundException",
    "ClassroomConflictException",
    "TeacherConflictException",
    "StudentConflictException",
    "DuplicateLessonException",
    "InvalidTimeRangeException",
    "InvalidLessonStatusException",
    "PermissionDeniedException",
    "StudioNotFoundException",
    "ClassroomNotFoundException",
    "UserNotFoundException",
    "GenerationException",
    "LessonImmutableException",
]
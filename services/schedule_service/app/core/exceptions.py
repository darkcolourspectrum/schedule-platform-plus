"""
Custom exceptions for Schedule Service
"""

from typing import Optional


class ScheduleServiceException(Exception):
    """Базовое исключение для Schedule Service"""
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class RecurringPatternNotFoundException(ScheduleServiceException):
    """Шаблон повторения не найден"""
    def __init__(self, pattern_id: int):
        super().__init__(
            message=f"Recurring pattern with id {pattern_id} not found"
        )


class LessonNotFoundException(ScheduleServiceException):
    """Занятие не найдено"""
    def __init__(self, lesson_id: int):
        super().__init__(
            message=f"Lesson with id {lesson_id} not found"
        )


class ClassroomConflictException(ScheduleServiceException):
    """Конфликт кабинета"""
    def __init__(self, classroom_id: int, lesson_date: str, time: str):
        super().__init__(
            message=f"Classroom {classroom_id} is already booked on {lesson_date} at {time}",
            details="Another lesson is scheduled in this classroom at the same time"
        )


class InvalidTimeRangeException(ScheduleServiceException):
    """Невалидный временной диапазон"""
    def __init__(self, message: str):
        super().__init__(message=message)


class InvalidLessonStatusException(ScheduleServiceException):
    """Невалидный статус занятия"""
    def __init__(self, current_status: str, new_status: str):
        super().__init__(
            message=f"Cannot change lesson status from '{current_status}' to '{new_status}'"
        )


class PermissionDeniedException(ScheduleServiceException):
    """Недостаточно прав"""
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message=message)


class StudioNotFoundException(ScheduleServiceException):
    """Студия не найдена"""
    def __init__(self, studio_id: int):
        super().__init__(
            message=f"Studio with id {studio_id} not found"
        )


class ClassroomNotFoundException(ScheduleServiceException):
    """Кабинет не найден"""
    def __init__(self, classroom_id: int):
        super().__init__(
            message=f"Classroom with id {classroom_id} not found"
        )


class UserNotFoundException(ScheduleServiceException):
    """Пользователь не найден"""
    def __init__(self, user_id: int):
        super().__init__(
            message=f"User with id {user_id} not found"
        )


class GenerationException(ScheduleServiceException):
    """Ошибка генерации занятий"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message=message, details=details)

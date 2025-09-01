from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class ScheduleException(HTTPException):
    """Базовое исключение для Schedule Service"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class StudioNotFoundException(ScheduleException):
    """Студия не найдена"""
    
    def __init__(self, studio_id: Optional[int] = None):
        detail = "Studio not found"
        if studio_id:
            detail += f" (ID: {studio_id})"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class RoomNotFoundException(ScheduleException):
    """Кабинет не найден"""
    
    def __init__(self, room_id: Optional[int] = None):
        detail = "Room not found"
        if room_id:
            detail += f" (ID: {room_id})"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class LessonNotFoundException(ScheduleException):
    """Урок не найден"""
    
    def __init__(self, lesson_id: Optional[int] = None):
        detail = "Lesson not found"
        if lesson_id:
            detail += f" (ID: {lesson_id})"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class TimeSlotConflictException(ScheduleException):
    """Конфликт времени - слот уже занят"""
    
    def __init__(self, room_name: Optional[str] = None, time_info: Optional[str] = None):
        detail = "Time slot is already occupied"
        if room_name and time_info:
            detail += f" in room '{room_name}' at {time_info}"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class InvalidTimeSlotException(ScheduleException):
    """Некорректный временной слот"""
    
    def __init__(self, reason: str = "Invalid time slot"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason
        )


class UnauthorizedStudioAccessException(ScheduleException):
    """Нет доступа к студии"""
    
    def __init__(self, studio_name: Optional[str] = None):
        detail = "Access denied to studio"
        if studio_name:
            detail += f" '{studio_name}'"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class LessonPermissionDeniedException(ScheduleException):
    """Нет прав для редактирования урока"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: you can only edit your own lessons"
        )


class InvalidScheduleRangeException(ScheduleException):
    """Некорректный диапазон расписания"""
    
    def __init__(self, max_weeks: int):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schedule range is limited to {max_weeks} weeks"
        )


class AuthServiceUnavailableException(ScheduleException):
    """Auth Service недоступен"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable"
        )


class ValidationException(ScheduleException):
    """Ошибка валидации данных"""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )
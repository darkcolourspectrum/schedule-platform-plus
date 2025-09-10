"""
Кастомные исключения для Profile Service
"""

from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class ProfileException(HTTPException):
    """Базовое исключение для Profile Service"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class ProfileNotFoundException(ProfileException):
    """Профиль не найден"""
    
    def __init__(self, user_id: Optional[int] = None):
        detail = "Profile not found"
        if user_id:
            detail = f"Profile for user {user_id} not found"
        
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class ProfileAlreadyExistsException(ProfileException):
    """Профиль уже существует"""
    
    def __init__(self, user_id: Optional[int] = None):
        detail = "Profile already exists"
        if user_id:
            detail = f"Profile for user {user_id} already exists"
        
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class ProfileAccessDeniedException(ProfileException):
    """Доступ к профилю запрещен"""
    
    def __init__(self, reason: str = "Access denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason
        )


class AvatarUploadException(ProfileException):
    """Ошибка загрузки аватара"""
    
    def __init__(self, reason: str = "Avatar upload failed"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason
        )


class AvatarSizeException(AvatarUploadException):
    """Превышен размер аватара"""
    
    def __init__(self, max_size_mb: int):
        super().__init__(f"Avatar size exceeds maximum allowed size of {max_size_mb}MB")


class AvatarTypeException(AvatarUploadException):
    """Недопустимый тип файла аватара"""
    
    def __init__(self, allowed_types: list):
        super().__init__(f"Invalid file type. Allowed types: {', '.join(allowed_types)}")


class CommentNotFoundException(ProfileException):
    """Комментарий не найден"""
    
    def __init__(self, comment_id: Optional[int] = None):
        detail = "Comment not found"
        if comment_id:
            detail = f"Comment {comment_id} not found"
        
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class CommentAccessDeniedException(ProfileException):
    """Доступ к комментарию запрещен"""
    
    def __init__(self, reason: str = "You can only modify your own comments"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason
        )


class CommentModerationException(ProfileException):
    """Комментарий заблокирован модератором"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail="Comment is locked by moderator"
        )


class ValidationException(ProfileException):
    """Ошибка валидации данных"""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class RateLimitException(ProfileException):
    """Превышен лимит запросов"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds",
            headers={"Retry-After": str(retry_after)}
        )


class AuthServiceUnavailableException(ProfileException):
    """Auth Service недоступен"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable"
        )


class CacheServiceException(ProfileException):
    """Ошибка кэш-сервиса"""
    
    def __init__(self, detail: str = "Cache service error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class DatabaseException(ProfileException):
    """Ошибка базы данных"""
    
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class ConfigurationException(ProfileException):
    """Ошибка конфигурации"""
    
    def __init__(self, detail: str = "Service configuration error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class BusinessLogicException(ProfileException):
    """Ошибка бизнес-логики"""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
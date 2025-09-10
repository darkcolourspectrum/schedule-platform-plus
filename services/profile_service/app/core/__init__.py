"""
Ядро Profile Service
"""

from app.core.exceptions import (
    ProfileException,
    ProfileNotFoundException,
    ProfileAlreadyExistsException,
    ProfileAccessDeniedException,
    AvatarUploadException,
    AvatarSizeException,
    AvatarTypeException,
    CommentNotFoundException,
    CommentAccessDeniedException,
    ValidationException,
    RateLimitException,
    AuthServiceUnavailableException
)

from app.core.auth import AuthManager, PermissionChecker

from app.core.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    RequestIDMiddleware,
    ErrorHandlingMiddleware
)

__all__ = [
    # Исключения
    "ProfileException",
    "ProfileNotFoundException", 
    "ProfileAlreadyExistsException",
    "ProfileAccessDeniedException",
    "AvatarUploadException",
    "AvatarSizeException",
    "AvatarTypeException",
    "CommentNotFoundException",
    "CommentAccessDeniedException",
    "ValidationException",
    "RateLimitException",
    "AuthServiceUnavailableException",
    
    # Аутентификация и авторизация
    "AuthManager",
    "PermissionChecker",
    
    # Middleware
    "LoggingMiddleware",
    "RateLimitMiddleware", 
    "SecurityHeadersMiddleware",
    "RequestIDMiddleware",
    "ErrorHandlingMiddleware"
]
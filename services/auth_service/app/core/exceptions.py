from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class AuthException(HTTPException):
    """Базовое исключение для аутентификации"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class InvalidCredentialsException(AuthException):
    """Неверные учетные данные"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )


class TokenExpiredException(AuthException):
    """Токен истек"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )


class InvalidTokenException(AuthException):
    """Недействительный токен"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


class TokenBlacklistedException(AuthException):
    """Токен в черном списке"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"}
        )


class UserNotFoundException(AuthException):
    """Пользователь не найден"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )


class UserAlreadyExistsException(AuthException):
    """Пользователь уже существует"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )


class UserInactiveException(AuthException):
    """Пользователь заблокирован"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )


class AccountLockedException(AuthException):
    """Аккаунт временно заблокирован"""
    
    def __init__(self, locked_until: Optional[str] = None):
        detail = "Account is temporarily locked"
        if locked_until:
            detail += f" until {locked_until}"
        
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail=detail
        )


class PermissionDeniedException(AuthException):
    """Недостаточно прав"""
    
    def __init__(self, required_role: str = ""):
        detail = "Permission denied"
        if required_role:
            detail += f". Required role: {required_role}"
        
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class RateLimitExceededException(AuthException):
    """Превышен лимит запросов"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds",
            headers={"Retry-After": str(retry_after)}
        )


class PrivacyPolicyNotAcceptedException(AuthException):
    """Политика конфиденциальности не принята"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Privacy policy must be accepted"
        )


class ValidationException(AuthException):
    """Ошибка валидации данных"""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )
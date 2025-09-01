from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_async_session
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.studio_service import StudioService
from app.core.security import TokenPayload
from app.core.exceptions import (
    InvalidTokenException,
    TokenBlacklistedException,
    PermissionDeniedException
)
from app.models.user import User
from app.models.role import RoleType

security = HTTPBearer(auto_error=False)


async def get_auth_service(db: AsyncSession = Depends(get_async_session)) -> AuthService:
    """Dependency для получения AuthService"""
    return AuthService(db)


async def get_user_service(db: AsyncSession = Depends(get_async_session)) -> UserService:
    """Dependency для получения UserService"""
    return UserService(db)


async def get_studio_service(db: AsyncSession = Depends(get_async_session)) -> StudioService:
    """Dependency для получения StudioService"""
    return StudioService(db)


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[User]:
    """
    Dependency для получения текущего пользователя (опционально)
    Возвращает None если токен не предоставлен или невалиден
    """
    if not credentials:
        return None
    
    try:
        token_payload = await auth_service.validate_access_token(credentials.credentials)
        user = await auth_service.get_current_user(token_payload)
        return user
    except:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """Dependency для получения текущего авторизованного пользователя"""
    if not credentials:
        raise InvalidTokenException()
    
    try:
        token_payload = await auth_service.validate_access_token(credentials.credentials)
        user = await auth_service.get_current_user(token_payload)
        return user
    except Exception as e:
        if isinstance(e, (InvalidTokenException, TokenBlacklistedException)):
            raise e
        raise InvalidTokenException()


async def get_current_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> TokenPayload:
    """Dependency для получения payload текущего токена"""
    if not credentials:
        raise InvalidTokenException()
    
    return await auth_service.validate_access_token(credentials.credentials)


async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency для проверки роли администратора"""
    if not current_user.is_admin:
        raise PermissionDeniedException(required_role="admin")
    return current_user


async def get_current_teacher(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency для проверки роли преподавателя или администратора"""
    if not (current_user.is_admin or current_user.is_teacher):
        raise PermissionDeniedException(required_role="teacher or admin")
    return current_user


async def get_current_student(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency для проверки любой авторизованной роли"""
    # Все авторизованные пользователи могут быть студентами
    return current_user


def get_client_info(request: Request) -> dict:
    """Получение информации о клиенте из запроса"""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
        "device_info": request.headers.get("X-Device-Info")  # Кастомный заголовок для устройства
    }


async def rate_limit_check(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
) -> None:
    """
    Простая проверка rate limiting
    В production рекомендуется использовать Redis или специализированные решения
    """
    # Базовая реализация - можно расширить
    client_ip = request.client.host if request.client else "unknown"
    
    # Здесь можно добавить логику rate limiting
    # Например, с использованием Redis для подсчета запросов
    pass
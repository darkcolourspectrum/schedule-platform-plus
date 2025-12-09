"""Dependencies для Auth Service"""
from typing import Optional
from fastapi import Depends, HTTPException, Request, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_async_session
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.repositories.user_repository import UserRepository
from app.repositories.role_repository import RoleRepository
from app.core.security import TokenPayload
from app.core.exceptions import (
    InvalidTokenException,
    TokenBlacklistedException,
    PermissionDeniedException
)
from app.models.user import User
from app.config import settings

security = HTTPBearer(auto_error=False)


# Service dependencies

async def get_user_repository(
    db: AsyncSession = Depends(get_async_session)
) -> UserRepository:
    """Dependency для получения UserRepository"""
    return UserRepository(db)


async def get_role_repository(
    db: AsyncSession = Depends(get_async_session)
) -> RoleRepository:
    """Dependency для получения RoleRepository"""
    return RoleRepository(db)


async def get_auth_service(
    db: AsyncSession = Depends(get_async_session)
) -> AuthService:
    """Dependency для получения AuthService"""
    return AuthService(db)


async def get_user_service(
    db: AsyncSession = Depends(get_async_session)
) -> UserService:
    """Dependency для получения UserService"""
    return UserService(db)


# Auth dependencies

async def verify_internal_api_key(
    x_internal_api_key: Optional[str] = Header(None)
) -> bool:
    """
    Проверка Internal API Key для межсервисного взаимодействия
    
    Args:
        x_internal_api_key: Ключ из заголовка X-Internal-API-Key
        
    Returns:
        True если ключ валиден
        
    Raises:
        HTTPException: Если ключ отсутствует или невалиден
    """
    if not x_internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal API key required",
            headers={"WWW-Authenticate": "X-Internal-API-Key"}
        )
    
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key"
        )
    
    return True


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
    """Dependency для проверки роли преподавателя"""
    if not (current_user.is_teacher or current_user.is_admin):
        raise PermissionDeniedException(required_role="teacher")
    return current_user


def get_client_info(request: Request) -> dict:
    """
    Получение информации о клиенте
    
    Args:
        request: FastAPI Request
        
    Returns:
        Dict с информацией о клиенте
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else "unknown"
    
    return {
        "ip_address": ip_address,
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "device_info": request.headers.get("User-Agent", "unknown")
    }
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_async_session
from app.services.schedule_service import ScheduleService
from app.services.auth_integration import auth_service
from app.core.exceptions import AuthServiceUnavailableException

security = HTTPBearer(auto_error=False)


class CurrentUser:
    """Модель текущего авторизованного пользователя"""
    
    def __init__(self, user_data: Dict[str, Any]):
        self.id: int = user_data["user_id"]
        self.email: str = user_data["email"]
        self.role: str = user_data["role"]
        self.studio_id: Optional[int] = user_data.get("studio_id")
        self.first_name: str = user_data.get("first_name", "")
        self.last_name: str = user_data.get("last_name", "")
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
    
    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"
    
    @property
    def is_student(self) -> bool:
        return self.role == "student"
    
    def has_studio_access(self, studio_id: int) -> bool:
        """Проверка доступа к студии"""
        if self.is_admin:
            return True
        
        if self.is_teacher and self.studio_id:
            # Преподаватель имеет доступ к своей студии
            # TODO: В будущем можно добавить поддержку множественных студий
            return self.studio_id == studio_id
        
        return False


async def get_schedule_service(db: AsyncSession = Depends(get_async_session)) -> ScheduleService:
    """Dependency для получения ScheduleService"""
    return ScheduleService(db)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[CurrentUser]:
    """
    Получение текущего пользователя (опционально)
    Возвращает None если токен не предоставлен или недействителен
    """
    if not credentials:
        return None
    
    try:
        user_data = await auth_service.validate_user_token(credentials.credentials)
        if user_data:
            return CurrentUser(user_data)
        return None
    except AuthServiceUnavailableException:
        # Если Auth Service недоступен, но токен есть - возвращаем None
        return None
    except Exception:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> CurrentUser:
    """Получение текущего авторизованного пользователя (обязательно)"""
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        user_data = await auth_service.validate_user_token(credentials.credentials)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return CurrentUser(user_data)
        
    except AuthServiceUnavailableException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Проверка прав администратора"""
    
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user


async def get_current_teacher(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Проверка прав преподавателя или администратора"""
    
    if not (current_user.is_admin or current_user.is_teacher):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher or admin access required"
        )
    
    return current_user


async def get_current_student(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Проверка авторизации (любая роль)"""
    # Все авторизованные пользователи могут выполнять действия студентов
    return current_user


def get_client_info(request: Request) -> Dict[str, Any]:
    """Получение информации о клиенте"""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
        "forwarded_for": request.headers.get("X-Forwarded-For")
    }


def verify_studio_access(
    studio_id: int,
    current_user: CurrentUser = Depends(get_current_user)
) -> None:
    """Проверка доступа к конкретной студии"""
    
    if not current_user.has_studio_access(studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to studio {studio_id}"
        )
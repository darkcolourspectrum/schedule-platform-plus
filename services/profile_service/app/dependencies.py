"""
Зависимости для Profile Service
"""

import logging
from typing import Optional, Dict, Any, Annotated
from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_database_session
from app.services.auth_client import auth_client
from app.services.profile_service import ProfileService
from app.services.avatar_service import avatar_service

logger = logging.getLogger(__name__)

def extract_role_name(role_data) -> str:
    """
    Универсальная функция для извлечения имени роли
    Работает и со старым форматом (dict) и с новым (string)
    
    Args:
        role_data: Данные роли - может быть str, dict или None
        
    Returns:
        Имя роли как строка
    """
    if role_data is None:
        return "student"
    if isinstance(role_data, str):
        return role_data
    if isinstance(role_data, dict):
        return role_data.get("name", "student")
    return "student"

# Типы для аннотаций
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


async def get_profile_service(db: DatabaseSession) -> ProfileService:
    """Dependency для получения ProfileService"""
    return ProfileService(db)


# Аутентификация и авторизация

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[int] = Header(None)  # Для внутренних запросов
) -> Dict[str, Any]:
    """
    Получение текущего пользователя из токена или заголовка
    
    Args:
        authorization: Bearer токен
        x_user_id: ID пользователя для внутренних запросов
        
    Returns:
        Словарь с данными пользователя
        
    Raises:
        HTTPException: Если пользователь не найден или токен невалиден
    """
    try:
        # Если передан X-User-ID (внутренний запрос)
        if x_user_id:
            user_data = await auth_client.get_user_by_id(x_user_id)
            if user_data:
                return user_data
        
        # Если передан Authorization токен
        if authorization:
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header format"
                )
            
            token = authorization.split(" ")[1]
            token_data = await auth_client.validate_token(token)
            
            if not token_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            user_id = token_data.get("user_id")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token does not contain user_id"
                )
            
            user_data = await auth_client.get_user_by_id(user_id)
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            return user_data
        
        # Нет аутентификационных данных
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка аутентификации: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


async def get_optional_current_user(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[int] = Header(None)
) -> Optional[Dict[str, Any]]:
    """
    Получение текущего пользователя (опционально)
    Не вызывает ошибку если пользователь не аутентифицирован
    """
    try:
        return await get_current_user(authorization, x_user_id)
    except HTTPException:
        return None


# Проверка ролей

async def require_role(required_roles: list[str]):
    """
    Dependency factory для проверки ролей пользователя
    
    Args:
        required_roles: Список разрешенных ролей
        
    Returns:
        Dependency function
    """
    async def check_role(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = extract_role_name(current_user.get("role"))
        
        if user_role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {' or '.join(required_roles)}"
            )
        
        return current_user
    
    return check_role


# Специализированные dependency для ролей

async def get_current_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency для проверки роли администратора"""
    user_role = extract_role_name(current_user.get("role"))
    
    if user_role not in ["admin", "moderator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or moderator role required"
        )
    
    return current_user


async def get_current_teacher(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency для проверки роли преподавателя"""
    user_role = extract_role_name(current_user.get("role"))
    
    if user_role not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher role required"
        )
    
    return current_user


async def get_current_student(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency для проверки роли студента"""
    user_role = extract_role_name(current_user.get("role"))
    
    if user_role not in ["student", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required"
        )
    
    return current_user


# Проверка доступа к ресурсам

async def verify_profile_access(
    user_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Проверка доступа к профилю пользователя
    
    Args:
        user_id: ID пользователя, чей профиль запрашивается
        current_user: Текущий пользователь
        
    Returns:
        Данные текущего пользователя
        
    Raises:
        HTTPException: Если доступ запрещен
    """
    current_user_id = current_user.get("id")
    current_user_role = extract_role_name(current_user.get("role"))
    
    # Администраторы видят все профили
    if current_user_role in ["admin", "moderator"]:
        return current_user
    
    # Пользователи видят только свои профили
    if current_user_id == user_id:
        return current_user
    
    # Для остальных случаев проверяем публичность профиля
    # (Эта проверка будет в самом endpoint с получением профиля)
    return current_user


# Валидация параметров

def validate_pagination(
    limit: int = 20,
    offset: int = 0
) -> Dict[str, int]:
    """
    Валидация параметров пагинации
    
    Args:
        limit: Максимальное количество элементов
        offset: Смещение
        
    Returns:
        Словарь с валидными параметрами пагинации
        
    Raises:
        HTTPException: Если параметры невалидны
    """
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100"
        )
    
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset must be non-negative"
        )
    
    return {"limit": limit, "offset": offset}


# Типы для аннотаций dependencies
CurrentUser = Annotated[Dict[str, Any], Depends(get_current_user)]
OptionalCurrentUser = Annotated[Optional[Dict[str, Any]], Depends(get_optional_current_user)]
CurrentAdmin = Annotated[Dict[str, Any], Depends(get_current_admin)]
CurrentTeacher = Annotated[Dict[str, Any], Depends(get_current_teacher)]
CurrentStudent = Annotated[Dict[str, Any], Depends(get_current_student)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
PaginationParams = Annotated[Dict[str, int], Depends(validate_pagination)]
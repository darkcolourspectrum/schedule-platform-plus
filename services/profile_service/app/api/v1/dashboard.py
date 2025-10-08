"""
API endpoints для персонализированных дашбордов
"""

import logging
from typing import Union
from fastapi import APIRouter, HTTPException, status, Path, Query
from fastapi.responses import JSONResponse

from app.dependencies import CurrentUser, DashboardServiceDep
from app.schemas.dashboard import (
    DashboardResponse, StudentDashboard, TeacherDashboard, 
    AdminDashboard, DefaultDashboard, DashboardError
)
from app.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/{user_id}",
    response_model=DashboardResponse,
    summary="Получение дашборда",
    description="Получение персонализированного дашборда пользователя"
)
async def get_user_dashboard(
    user_id: int = Path(..., description="ID пользователя"),
    force_refresh: bool = Query(False, description="Принудительное обновление кэша"),
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Получение персонализированного дашборда пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        # Пользователи могут видеть только свой дашборд, админы - любой
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own dashboard"
            )
        
        # Очищаем кэш если запрошено принудительное обновление
        if force_refresh:
            from app.services.cache_service import cache_service
            user_role = current_user.get("role", {}).get("name", "") if current_user_id == user_id else None
            if user_role:
                cache_key = f"dashboard:{user_role}:{user_id}"
                await cache_service.delete(cache_key)
        
        # Получаем дашборд
        dashboard_data = await dashboard_service.get_dashboard(user_id)
        
        if dashboard_data.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=dashboard_data["error"]
            )
        
        # Определяем, был ли результат получен из кэша
        cached = not force_refresh
        
        return DashboardResponse(
            user_info=dashboard_data["user_info"],
            role=dashboard_data["role"],
            dashboard_type=dashboard_data["dashboard_type"],
            data=dashboard_data,
            cached=cached
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения дашборда для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@router.get(
    "/student/{user_id}",
    response_model=StudentDashboard,
    summary="Дашборд студента",
    description="Получение специализированного дашборда для студента"
)
async def get_student_dashboard(
    user_id: int = Path(..., description="ID студента"),
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Получение дашборда студента"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Получаем дашборд и проверяем роль
        dashboard_data = await dashboard_service.get_dashboard(user_id, "student")
        
        if dashboard_data.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=dashboard_data["error"]
            )
        
        if dashboard_data.get("dashboard_type") != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a student"
            )
        
        return StudentDashboard(**dashboard_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения дашборда студента {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load student dashboard"
        )


@router.get(
    "/teacher/{user_id}",
    response_model=TeacherDashboard,
    summary="Дашборд преподавателя",
    description="Получение специализированного дашборда для преподавателя"
)
async def get_teacher_dashboard(
    user_id: int = Path(..., description="ID преподавателя"),
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Получение дашборда преподавателя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Получаем дашборд и проверяем роль
        dashboard_data = await dashboard_service.get_dashboard(user_id, "teacher")
        
        if dashboard_data.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=dashboard_data["error"]
            )
        
        if dashboard_data.get("dashboard_type") != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a teacher"
            )
        
        return TeacherDashboard(**dashboard_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения дашборда преподавателя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load teacher dashboard"
        )


@router.get(
    "/admin/{user_id}",
    response_model=AdminDashboard,
    summary="Дашборд администратора",
    description="Получение специализированного дашборда для администратора"
)
async def get_admin_dashboard(
    user_id: int = Path(..., description="ID администратора"),
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Получение дашборда администратора"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        # Только администраторы могут видеть админский дашборд
        if current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required"
            )
        
        if current_user_id != user_id and current_user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Получаем дашборд и проверяем роль
        dashboard_data = await dashboard_service.get_dashboard(user_id, "admin")
        
        if dashboard_data.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=dashboard_data["error"]
            )
        
        if dashboard_data.get("dashboard_type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not an admin"
            )
        
        return AdminDashboard(**dashboard_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения дашборда администратора {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load admin dashboard"
        )


@router.delete(
    "/{user_id}/cache",
    response_model=SuccessResponse,
    summary="Очистка кэша дашборда",
    description="Принудительная очистка кэша дашборда пользователя"
)
async def clear_dashboard_cache(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Очистка кэша дашборда пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only clear your own dashboard cache"
            )
        
        # Очищаем кэш дашборда
        from app.services.cache_service import cache_service
        
        # Очищаем все возможные варианты кэша дашборда для пользователя
        cache_patterns = [
            f"dashboard:student:{user_id}",
            f"dashboard:teacher:{user_id}",
            f"dashboard:admin:{user_id}",
            f"dashboard:*:{user_id}"
        ]
        
        total_cleared = 0
        for pattern in cache_patterns:
            if "*" in pattern:
                cleared = await cache_service.clear_pattern(pattern)
            else:
                cleared = 1 if await cache_service.delete(pattern) else 0
            total_cleared += cleared
        
        logger.info(f"Очищен кэш дашборда пользователя {user_id}: {total_cleared} ключей")
        
        return SuccessResponse(
            message=f"Dashboard cache cleared: {total_cleared} keys removed"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка очистки кэша дашборда пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear dashboard cache"
        )


@router.get(
    "/stats/system",
    response_model=dict,
    summary="Системная статистика",
    description="Получение общей статистики системы (только для администраторов)"
)
async def get_system_stats(
    current_user: CurrentUser = ...,
    dashboard_service: DashboardServiceDep = ...
):
    """Получение системной статистики (только администраторы)"""
    try:
        # ИСПРАВЛЕНИЕ: Проверяем что current_user это словарь
        if not isinstance(current_user, dict):
            logger.error(f"current_user не является словарем: {type(current_user)}, значение: {current_user}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid user data format"
            )
        
        # Проверяем права администратора
        user_role = current_user.get("role")
        
        # Обрабатываем разные форматы role
        if isinstance(user_role, dict):
            current_user_role = user_role.get("name", "")
        elif isinstance(user_role, str):
            current_user_role = user_role
        else:
            logger.error(f"Неожиданный формат role: {type(user_role)}, значение: {user_role}")
            current_user_role = ""
        
        logger.info(f"Проверка прав для пользователя ID={current_user.get('id')}, роль={current_user_role}")
        
        if current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Admin role required. Your role: {current_user_role}"
            )
        
        # Получаем системную статистику через приватный метод сервиса
        stats = await dashboard_service._get_system_statistics()
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения системной статистики: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load system statistics: {str(e)}"
        )
"""
API endpoints для работы с профилями пользователей
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query, Path
from fastapi.responses import JSONResponse

from app.dependencies import (
    CurrentUser, OptionalCurrentUser, CurrentAdmin,
    ProfileServiceDep, PaginationParams,
    verify_profile_access
)
from app.schemas.profile import (
    ProfileCreate, ProfileUpdate, ProfileResponse, ProfilePublicResponse,
    ProfileSearchResult, ProfileListResponse, NotificationPreferences,
    ProfileSettings, ProfileStatsResponse, MessageResponse
)
from app.schemas.common import SuccessResponse, ErrorResponse
from app.models.activity import ActivityType, ActivityLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.post(
    "/",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание профиля",
    description="Создание нового профиля пользователя"
)
async def create_profile(
    profile_data: ProfileCreate,
    current_user: CurrentUser,
    profile_service: ProfileServiceDep
):
    """Создание профиля для текущего пользователя"""
    try:
        user_id = current_user["id"]
        
        # Проверяем, что профиль еще не существует
        existing_profile = await profile_service.get_profile_by_user_id(user_id)
        if existing_profile and not existing_profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Profile already exists"
            )
        
        # Создаем профиль
        profile = await profile_service.create_profile(
            user_id=user_id,
            **profile_data.dict(exclude_unset=True)
        )
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create profile"
            )
        
        # Получаем полный профиль для ответа
        full_profile = await profile_service.get_profile_by_user_id(user_id, user_id)
        
        logger.info(f"Создан профиль для пользователя {user_id}")
        return full_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка создания профиля: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{user_id}",
    response_model=ProfileResponse,
    summary="Получение профиля",
    description="Получение профиля пользователя по ID"
)
async def get_profile(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: OptionalCurrentUser,
    profile_service: ProfileServiceDep
):
    """Получение профиля пользователя"""
    try:
        viewer_user_id = current_user["id"] if current_user else None
        
        # Получаем профиль
        profile = await profile_service.get_profile_by_user_id(user_id, viewer_user_id)
        
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Проверяем права доступа к приватным данным
        is_owner = viewer_user_id == user_id
        is_admin = (current_user and 
                   current_user.get("role", {}).get("name") in ["admin", "moderator"])
        
        if not is_owner and not is_admin and not profile.get("is_profile_public", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Profile is private"
            )
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения профиля {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put(
    "/{user_id}",
    response_model=ProfileResponse,
    summary="Обновление профиля",
    description="Обновление профиля пользователя"
)
async def update_profile(
    user_id: int = Path(..., description="ID пользователя"),
    profile_data: ProfileUpdate = ...,
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Обновление профиля пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile"
            )
        
        # Обновляем профиль
        update_data = profile_data.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data provided for update"
            )
        
        updated_profile = await profile_service.update_profile(user_id, **update_data)
        
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Получаем обновленный полный профиль
        full_profile = await profile_service.get_profile_by_user_id(user_id, current_user_id)
        
        logger.info(f"Обновлен профиль пользователя {user_id}")
        return full_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления профиля {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.patch(
    "/{user_id}/notifications",
    response_model=SuccessResponse,
    summary="Обновление настроек уведомлений",
    description="Обновление настроек уведомлений пользователя"
)
async def update_notification_preferences(
    user_id: int = Path(..., description="ID пользователя"),
    preferences: NotificationPreferences = ...,
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Обновление настроек уведомлений"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        
        if current_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own notification preferences"
            )
        
        # Обновляем настройки
        updated_profile = await profile_service.update_notification_preferences(
            user_id, preferences.dict()
        )
        
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        return SuccessResponse(
            message="Notification preferences updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления настроек уведомлений {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.patch(
    "/{user_id}/settings",
    response_model=SuccessResponse,
    summary="Обновление настроек профиля",
    description="Обновление настроек профиля пользователя"
)
async def update_profile_settings(
    user_id: int = Path(..., description="ID пользователя"),
    settings: ProfileSettings = ...,
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Обновление настроек профиля"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        
        if current_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile settings"
            )
        
        # Обновляем настройки
        updated_profile = await profile_service.update_profile_settings(
            user_id, settings.dict()
        )
        
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        return SuccessResponse(
            message="Profile settings updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления настроек профиля {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/",
    response_model=ProfileListResponse,
    summary="Список публичных профилей",
    description="Получение списка публичных профилей с пагинацией"
)
async def get_public_profiles(
    pagination: PaginationParams,
    profile_service: ProfileServiceDep
):
    """Получение списка публичных профилей"""
    try:
        profiles = await profile_service.get_public_profiles(
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        # Подсчитываем общее количество (для упрощения используем length результата)
        total = len(profiles)
        has_more = len(profiles) == pagination["limit"]
        
        return ProfileListResponse(
            profiles=profiles,
            total=total,
            limit=pagination["limit"],
            offset=pagination["offset"],
            has_more=has_more
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения списка профилей: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/search",
    response_model=List[ProfileSearchResult],
    summary="Поиск профилей",
    description="Поиск профилей по имени или биографии"
)
async def search_profiles(
    query: str = Query(..., min_length=1, max_length=100, description="Поисковый запрос"),
    limit: int = Query(20, ge=1, le=100, description="Максимальное количество результатов"),
    profile_service: ProfileServiceDep = ...
):
    """Поиск профилей"""
    try:
        profiles = await profile_service.search_profiles(query, limit)
        
        return profiles
        
    except Exception as e:
        logger.error(f"Ошибка поиска профилей по запросу '{query}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{user_id}/stats",
    response_model=ProfileStatsResponse,
    summary="Статистика профиля",
    description="Получение статистики профиля пользователя"
)
async def get_profile_stats(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: OptionalCurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Получение статистики профиля"""
    try:
        # Проверяем существование профиля
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Проверяем права доступа к приватному профилю
        viewer_user_id = current_user["id"] if current_user else None
        is_owner = viewer_user_id == user_id
        is_admin = (current_user and 
                   current_user.get("role", {}).get("name") in ["admin", "moderator"])
        
        if not is_owner and not is_admin and not profile.get("is_profile_public", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Profile is private"
            )
        
        # Базовая статистика профиля
        stats = {
            "profile_views": profile.get("profile_views", 0),
            "total_comments": 0,  # Будет реализовано через CommentService
            "recent_activities_count": 0  # Будет реализовано через ActivityRepository
        }
        
        return ProfileStatsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения статистики профиля {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Удаление профиля",
    description="Удаление профиля пользователя (только для администраторов)"
)
async def delete_profile(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: CurrentAdmin = ...,
    profile_service: ProfileServiceDep = ...
):
    """Удаление профиля пользователя (только администраторы)"""
    try:
        # Проверяем существование профиля
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Здесь должна быть логика удаления профиля
        # Пока возвращаем заглушку
        logger.warning(f"Запрос на удаление профиля {user_id} от администратора {current_user['id']}")
        
        return MessageResponse(
            message="Profile deletion is not implemented yet",
            success=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления профиля {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
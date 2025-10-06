from typing import List
from fastapi import APIRouter, Depends, Query, status, HTTPException

from app.dependencies import (
    get_current_user,
    get_current_admin,
    get_user_service,
    verify_internal_api_key
)
from app.services.user_service import UserService
from app.schemas.user import UserProfile, UserListItem, UserUpdate
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/",
    response_model=List[UserListItem],
    summary="Получение списка пользователей",
    description="Доступно только администраторам или внутренним сервисам"
)
async def get_users(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    role: str = Query(None, description="Фильтр по роли"),
    studio_id: int = Query(None, description="Фильтр по студии"),
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service)
):
    """
    Получение списка пользователей
    
    ИСПРАВЛЕНО: Теперь требует X-Internal-API-Key вместо admin токена
    """
    
    return await user_service.get_users_list(
        limit=limit,
        offset=offset,
        role=role,
        studio_id=studio_id
    )


@router.get(
    "/profile",
    response_model=UserProfile,
    summary="Получение профиля текущего пользователя"
)
async def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    """Получение профиля текущего пользователя"""
    
    return UserProfile.from_orm(current_user)


@router.put(
    "/profile",
    response_model=UserProfile,
    summary="Обновление профиля текущего пользователя"
)
async def update_my_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """Обновление профиля текущего пользователя"""
    
    updated_user = await user_service.update_user_profile(
        user_id=current_user.id,
        update_data=profile_data
    )
    
    return UserProfile.from_orm(updated_user)


@router.get(
    "/{user_id}",
    response_model=UserProfile,
    summary="Получение профиля пользователя по ID",
    description="Доступно для внутренних сервисов с X-Internal-API-Key"
)
async def get_user_profile(
    user_id: int,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service)
):
    """
    Получение профиля пользователя по ID
    
    ИСПРАВЛЕНО: Теперь требует X-Internal-API-Key вместо Bearer токена
    Это позволяет другим микросервисам получать данные пользователей
    """
    
    user = await user_service.get_user_by_id(user_id)
    return UserProfile.from_orm(user)
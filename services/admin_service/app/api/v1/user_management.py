"""User Management API endpoints"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_admin
from app.services.user_management_service import UserManagementService
from app.schemas.user import (
    UserResponse,
    UserUpdateRequest,
    UserRoleUpdateRequest,
    UserStudioAssignRequest
)
from app.dependencies import get_user_management_service

router = APIRouter(prefix="/user-management", tags=["User Management"])


@router.get("", response_model=List[UserResponse])
async def get_all_users(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    role: Optional[str] = None,
    studio_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    current_user: dict = Depends(get_current_admin),
    service: UserManagementService = Depends(get_user_management_service)
):
    """Получить всех пользователей с фильтрами"""
    return await service.get_users_list(
        limit=limit,
        offset=offset,
        role=role,
        studio_id=studio_id,
        is_active=is_active
    )


@router.put("/{user_id}/role", response_model=dict)
async def update_user_role(
    user_id: int,
    request: UserRoleUpdateRequest,
    current_user: dict = Depends(get_current_admin),
    service: UserManagementService = Depends(get_user_management_service)
):
    """Изменить роль пользователя"""
    user = await service.update_user_role(user_id, request.role)
    return {
        "message": f"Role updated to {request.role}",
        "user": user
    }


@router.put("/{user_id}/studio", response_model=dict)
async def assign_user_to_studio(
    user_id: int,
    request: UserStudioAssignRequest,
    current_user: dict = Depends(get_current_admin),
    service: UserManagementService = Depends(get_user_management_service)
):
    """Привязать пользователя к студии"""
    user = await service.assign_user_to_studio(user_id, request.studio_id)
    return {
        "message": f"User assigned to studio {request.studio_id}",
        "user": user
    }


@router.post("/{user_id}/activate", response_model=dict)
async def activate_user(
    user_id: int,
    current_user: dict = Depends(get_current_admin),
    service: UserManagementService = Depends(get_user_management_service)
):
    """Активировать пользователя"""
    user = await service.activate_user(user_id)
    return {
        "message": "User activated",
        "user": user
    }


@router.post("/{user_id}/deactivate", response_model=dict)
async def deactivate_user(
    user_id: int,
    current_user: dict = Depends(get_current_admin),
    service: UserManagementService = Depends(get_user_management_service)
):
    """Деактивировать пользователя"""
    user = await service.deactivate_user(user_id)
    return {
        "message": "User deactivated",
        "user": user
    }

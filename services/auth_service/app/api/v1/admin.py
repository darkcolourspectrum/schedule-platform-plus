from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_admin, get_user_service
from app.services.user_service import UserService
from app.models.user import User
from app.schemas.admin import (
    AssignTeacherRequest,
    UserRoleUpdate,
    AdminUserResponse,
    StudioAssignmentRequest
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/users",
    response_model=List[AdminUserResponse],
    summary="Получение всех пользователей",
    description="Полный список пользователей для администрирования"
)
async def get_all_users(
    limit: int = 50,
    offset: int = 0,
    role: str = None,
    studio_id: int = None,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Получение списка всех пользователей с расширенной информацией"""
    
    users = await user_service.get_users_list(
        limit=limit,
        offset=offset,
        role=role,
        studio_id=studio_id
    )
    
    # Конвертируем в AdminUserResponse
    return [AdminUserResponse.from_user(user) for user in users if hasattr(user, 'role')]


@router.post(
    "/assign-teacher",
    summary="Назначение роли преподавателя",
    description="Назначение пользователю роли преподавателя с привязкой к студии"
)
async def assign_teacher_role(
    request: AssignTeacherRequest,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Назначение роли преподавателя пользователю"""
    
    result = await user_service.assign_teacher_role(
        user_id=request.user_id,
        studio_id=request.studio_id
    )
    
    return {
        "message": f"Пользователь {result.full_name} назначен преподавателем в студии",
        "user": {
            "id": result.id,
            "email": result.email,
            "full_name": result.full_name,
            "role": result.role.name,
            "studio_name": result.studio.name if result.studio else None
        }
    }


@router.post(
    "/change-user-role",
    summary="Изменение роли пользователя",
    description="Изменение роли любого пользователя"
)
async def change_user_role(
    request: UserRoleUpdate,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Изменение роли пользователя"""
    
    result = await user_service.change_user_role(
        user_id=request.user_id,
        new_role=request.role
    )
    
    return {
        "message": f"Роль пользователя {result.full_name} изменена на {result.role.name}",
        "user": {
            "id": result.id,
            "email": result.email,
            "full_name": result.full_name,
            "role": result.role.name
        }
    }


@router.post(
    "/assign-studio",
    summary="Привязка пользователя к студии",
    description="Назначение студии для преподавателя"
)
async def assign_user_to_studio(
    request: StudioAssignmentRequest,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Привязка пользователя к студии"""
    
    result = await user_service.assign_user_to_studio(
        user_id=request.user_id,
        studio_id=request.studio_id
    )
    
    return {
        "message": f"Пользователь {result.full_name} привязан к студии {result.studio.name}",
        "user": {
            "id": result.id,
            "email": result.email,
            "full_name": result.full_name,
            "studio_name": result.studio.name if result.studio else None
        }
    }


@router.delete(
    "/users/{user_id}",
    summary="Деактивация пользователя",
    description="Деактивация аккаунта пользователя (не удаление)"
)
async def deactivate_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Деактивация пользователя"""
    
    await user_service.deactivate_user(user_id)
    
    return {"message": "Пользователь деактивирован"}


@router.post(
    "/users/{user_id}/activate",
    summary="Активация пользователя",
    description="Активация деактивированного пользователя"
)
async def activate_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Активация пользователя"""
    
    result = await user_service.activate_user(user_id)
    
    return {
        "message": f"Пользователь {result.full_name} активирован",
        "user": {
            "id": result.id,
            "email": result.email,
            "full_name": result.full_name,
            "is_active": result.is_active
        }
    }
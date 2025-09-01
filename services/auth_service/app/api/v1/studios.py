from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_admin, get_current_teacher, get_studio_service
from app.services.studio_service import StudioService
from app.models.user import User
from app.schemas.admin import StudioCreate, StudioUpdate, StudioInfo

router = APIRouter(prefix="/studios", tags=["Studios"])


@router.get(
    "/",
    response_model=List[StudioInfo],
    summary="Получение списка студий",
    description="Доступно администраторам и преподавателям"
)
async def get_studios(
    current_user: User = Depends(get_current_teacher),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Получение списка студий с информацией"""
    
    # Администратор видит все студии, преподаватель - только свою
    if current_user.is_admin:
        return await studio_service.get_all_studios_with_stats()
    else:
        if not current_user.studio_id:
            return []
        studio = await studio_service.get_studio_with_stats(current_user.studio_id)
        return [studio] if studio else []


@router.post(
    "/",
    response_model=StudioInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Создание новой студии",
    description="Доступно только администраторам"
)
async def create_studio(
    studio_data: StudioCreate,
    admin_user: User = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Создание новой студии"""
    
    return await studio_service.create_studio(studio_data)


@router.get(
    "/{studio_id}",
    response_model=StudioInfo,
    summary="Получение информации о студии",
    description="Доступно администраторам и преподавателям студии"
)
async def get_studio(
    studio_id: int,
    current_user: User = Depends(get_current_teacher),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Получение детальной информации о студии"""
    
    # Проверка прав доступа
    if not current_user.is_admin and current_user.studio_id != studio_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this studio"
        )
    
    studio = await studio_service.get_studio_with_stats(studio_id)
    if not studio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio not found"
        )
    
    return studio


@router.put(
    "/{studio_id}",
    response_model=StudioInfo,
    summary="Обновление информации о студии",
    description="Доступно только администраторам"
)
async def update_studio(
    studio_id: int,
    update_data: StudioUpdate,
    admin_user: User = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Обновление информации о студии"""
    
    return await studio_service.update_studio(studio_id, update_data)


@router.delete(
    "/{studio_id}",
    summary="Деактивация студии",
    description="Доступно только администраторам"
)
async def deactivate_studio(
    studio_id: int,
    admin_user: User = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Деактивация студии (мягкое удаление)"""
    
    await studio_service.deactivate_studio(studio_id)
    return {"message": "Studio deactivated successfully"}


@router.post(
    "/{studio_id}/activate",
    summary="Активация студии",
    description="Доступно только администраторам"
)
async def activate_studio(
    studio_id: int,
    admin_user: User = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Активация студии"""
    
    studio = await studio_service.activate_studio(studio_id)
    return {
        "message": f"Studio '{studio.name}' activated successfully",
        "studio": {
            "id": studio.id,
            "name": studio.name,
            "is_active": studio.is_active
        }
    }


@router.get(
    "/{studio_id}/teachers",
    summary="Получение преподавателей студии",
    description="Доступно администраторам и преподавателям студии"
)
async def get_studio_teachers(
    studio_id: int,
    current_user: User = Depends(get_current_teacher),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Получение списка преподавателей конкретной студии"""
    
    # Проверка прав доступа
    if not current_user.is_admin and current_user.studio_id != studio_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this studio"
        )
    
    return await studio_service.get_studio_teachers(studio_id)
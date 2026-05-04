"""
API endpoints для studios (read-only из локального кеша Schedule Service).

Эти endpoints дают фронту независимый доступ к данным студий, кабинетов
и членов студии без обращения к Admin Service. Это решает проблему
прав: преподаватель не может ходить на admin-эндпоинты, но имеет полный
доступ к данным своей студии через эти endpoints.

Источник данных: локальные кеши studios_cache, classrooms_cache,
users_cache - синхронизируемые из Auth и Admin сервисов через события.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_async_session
from app.dependencies import get_current_user, check_studio_access
from app.services.membership_service import MembershipService
from app.schemas.membership import (
    StudioInfo,
    ClassroomInfo,
    StudioMemberInfo,
    StudioMembersResponse,
)

router = APIRouter(prefix="/studios", tags=["Studios (read-only)"])


def _get_membership_service(
    db: AsyncSession = Depends(get_async_session),
) -> MembershipService:
    return MembershipService(db)


@router.get(
    "",
    response_model=List[StudioInfo],
    summary="Список студий, доступных текущему пользователю",
)
async def list_studios(
    current_user: dict = Depends(get_current_user),
    service: MembershipService = Depends(_get_membership_service),
):
    """
    Список активных студий, доступных текущему пользователю.
    
    Admin: все активные студии.
    Teacher/Student: только их собственная студия.
    """
    studios = await service.get_studios_for_user(current_user)
    return studios


@router.get(
    "/{studio_id}/classrooms",
    response_model=List[ClassroomInfo],
    summary="Список активных кабинетов студии",
)
async def list_studio_classrooms(
    studio_id: int,
    current_user: dict = Depends(get_current_user),
    service: MembershipService = Depends(_get_membership_service),
):
    """
    Активные кабинеты студии.
    
    Доступ проверяется через check_studio_access:
    Admin может смотреть любую студию, остальные - только свою.
    """
    if not check_studio_access(current_user, studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this studio",
        )
    
    return await service.get_studio_classrooms(studio_id)


@router.get(
    "/{studio_id}/members",
    response_model=StudioMembersResponse,
    summary="Список преподавателей и учеников студии",
)
async def list_studio_members(
    studio_id: int,
    current_user: dict = Depends(get_current_user),
    service: MembershipService = Depends(_get_membership_service),
):
    """
    Преподаватели и ученики, привязанные к студии.
    
    Используется фронтом в модалках создания занятия и шаблона:
    выбрать преподавателя, выбрать учеников.
    
    Доступ проверяется через check_studio_access.
    """
    if not check_studio_access(current_user, studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this studio",
        )
    
    teachers = await service.get_studio_teachers(studio_id)
    students = await service.get_studio_students(studio_id)
    
    return StudioMembersResponse(
        studio_id=studio_id,
        teachers=[StudioMemberInfo.model_validate(t) for t in teachers],
        students=[StudioMemberInfo.model_validate(s) for s in students],
    )
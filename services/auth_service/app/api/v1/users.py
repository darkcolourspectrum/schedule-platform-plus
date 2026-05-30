from typing import List
from fastapi import APIRouter, Depends, Query, status, HTTPException

from app.dependencies import (
    get_current_user,
    get_current_admin,
    get_user_service,
    verify_internal_api_key
)
from app.services.user_service import UserService
from app.schemas.user import (
    UserProfile,
    UserListItem,
    UserUpdate,
    UserRoleUpdateRequest,
    UserStudioAssignRequest,
    UserProvisionRequest,
)
from app.repositories.role_repository import RoleRepository
from app.database.connection import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import UserNotFoundException, UserAlreadyExistsException
from app.models.user import User

from app.schemas.auth import VkLinkRequest
from app.schemas.user import UserProfile
from app.services.vk_id_client import vk_id_client, VkIdError
from fastapi.responses import JSONResponse

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

@router.post(
    "/{user_id}/link-vk",
    response_model=UserProfile,
    summary="Привязка VK к аккаунту",
    description=(
        "Привязывает VK к аккаунту текущего пользователя. Принимает "
        "code/device_id/code_verifier из окна VK, серверно обменивает их "
        "на проверенный vk_id и проставляет его пользователю. "
        "409 - этот VK уже привязан к другому аккаунту. "
        "Привязать можно только СВОЙ аккаунт (user_id из пути должен "
        "совпадать с текущим пользователем)."
    ),
)
async def link_vk(
    user_id: int,
    payload: VkLinkRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Привязка VK к своему аккаунту.

    Защита: user_id в пути обязан совпадать с id текущего пользователя -
    нельзя привязать VK к чужому аккаунту, даже зная его id.
    """
    if user_id != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "You can only link VK to your own account"},
        )

    # Обмен кода на проверенный vk_id.
    try:
        vk_result = await vk_id_client.exchange_code(
            code=payload.code,
            device_id=payload.device_id,
            code_verifier=payload.code_verifier,
            state=payload.state,
        )
    except VkIdError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"VK authorization failed: {exc}"},
        )

    # Привязка. Коллизия (VK занят другим) -> UserAlreadyExistsException (409).
    updated_user = await user_service.link_vk(
        user_id=user_id,
        vk_id=vk_result.vk_id,
    )
    return UserProfile.from_orm(updated_user)


@router.post(
    "/{user_id}/unlink-vk",
    response_model=UserProfile,
    summary="Отвязка VK от аккаунта",
    description=(
        "Снимает привязку VK у текущего пользователя. Отвязать можно "
        "только свой аккаунт."
    ),
)
async def unlink_vk(
    user_id: int,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    """Отвязка VK от своего аккаунта."""
    if user_id != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "You can only unlink VK from your own account"},
        )

    updated_user = await user_service.unlink_vk(user_id=user_id)
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

@router.put(
    "/{user_id}/profile",
    response_model=UserProfile,
    summary="Обновление профиля пользователя (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key"
)
async def update_user_profile_internal(
    user_id: int,
    profile_data: UserUpdate,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service)
):
    """
    Обновление профиля пользователя для внутренних сервисов
    
    Этот endpoint позволяет другим микросервисам
    обновлять данные пользователя в Auth Service
    """
    
    updated_user = await user_service.update_user_profile(
        user_id=user_id,
        update_data=profile_data
    )
    
    return UserProfile.from_orm(updated_user)

@router.put(
    "/{user_id}/role",
    response_model=UserProfile,
    summary="Изменение роли пользователя (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key"
)
async def change_user_role_internal(
    user_id: int,
    request: UserRoleUpdateRequest,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Изменение роли пользователя по имени роли.
    Публикует событие role.changed в outbox.
    """
    role_repo = RoleRepository(db)
    role = await role_repo.get_by_name(request.role)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{request.role}' not found",
        )
    
    updated_user = await user_service.change_user_role(
        user_id=user_id,
        new_role_id=role.id,
    )
    return UserProfile.from_orm(updated_user)


@router.put(
    "/{user_id}/studio",
    response_model=UserProfile,
    summary="Привязка пользователя к студии (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key"
)
async def assign_user_to_studio_internal(
    user_id: int,
    request: UserStudioAssignRequest,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service),
):
    """
    Привязка пользователя к студии. Публикует событие user.updated в outbox.
    """
    updated_user = await user_service.assign_user_to_studio(
        user_id=user_id,
        studio_id=request.studio_id,
    )
    return UserProfile.from_orm(updated_user)


@router.post(
    "/{user_id}/activate",
    response_model=UserProfile,
    summary="Активация пользователя (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key"
)
async def activate_user_internal(
    user_id: int,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service),
):
    """
    Активация пользователя. Публикует событие user.updated в outbox.
    """
    updated_user = await user_service.activate_user(user_id)
    return UserProfile.from_orm(updated_user)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserProfile,
    summary="Деактивация пользователя (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key"
)
async def deactivate_user_internal(
    user_id: int,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service),
):
    """
    Деактивация пользователя. Публикует событие user.deactivated в outbox.
    """
    updated_user = await user_service.deactivate_user(user_id)
    return UserProfile.from_orm(updated_user)

@router.post(
    "/provision",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Создание provisioned-пользователя (внутренний endpoint)",
    description="Доступно только для внутренних сервисов с X-Internal-API-Key. "
    "Создаёт аккаунт без пароля для лида, ставшего клиентом (используется "
    "CRM Service при конвертации лида).",
)
async def provision_user_internal(
    request: UserProvisionRequest,
    internal_key_valid: bool = Depends(verify_internal_api_key),
    user_service: UserService = Depends(get_user_service),
):
    """
    Создать provisioned-пользователя для внутреннего сервиса.

    Пользователь создаётся без пароля, с ролью студента. Публикует
    событие user.created в outbox.

    Возвращает 409, если email уже занят.
    """
    try:
        user = await user_service.provision_user(
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            studio_id=request.studio_id,
        )
    except UserAlreadyExistsException:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{request.email}' already exists",
        )

    return UserProfile.from_orm(user)
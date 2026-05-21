"""
API-эндпоинты для работы с лидами.

Маршрутизация: api-gateway проксирует /api/crm/<path> на этот сервис
как /api/v1/<path>. Роутер монтируется с prefix=/api/v1 в main.py,
поэтому снаружи пути выглядят как /api/crm/leads/...

Эндпоинты:
    POST   /leads/public               - публичный, приём заявки с лендинга
    GET    /leads                      - admin, список лидов с фильтрами
    GET    /leads/{id}                 - admin, карточка лида с журналом
    PATCH  /leads/{id}                 - admin, правка assigned_to/notes
    PATCH  /leads/{id}/status          - admin, смена статуса воронки
    POST   /leads/{id}/activities      - admin, добавить заметку/звонок
    POST   /leads/{id}/convert-to-user - admin, конвертация лида в клиента
    GET    /studios                    - admin, список активных студий
                                         (для select в модалке конвертации)

Роутер не ловит доменные исключения сам - их транслируют в HTTP-коды
централизованные exception handlers, зарегистрированные в main.py.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query, status

from app.core.enums import LeadStatus
from app.dependencies import get_current_admin, get_lead_service
from app.schemas.lead import (
    LeadActivityCreate,
    LeadActivityResponse,
    LeadConversionResponse,
    LeadConvertRequest,
    LeadDetailResponse,
    LeadListResponse,
    LeadPublicCreate,
    LeadResponse,
    LeadStatusUpdate,
    LeadUpdate,
    StudioOption,
)
from app.services.lead_service import LeadService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["Leads"])

# Отдельный роутер для справочников (без префикса /leads).
# Сейчас здесь только список студий из локального кеша - его дёргает
# модалка конвертации на фронте. Если справочников станет больше -
# имеет смысл вынести в отдельный файл api/v1/studios.py.
studios_router = APIRouter(prefix="/studios", tags=["Studios"])


# ==================== ПУБЛИЧНЫЙ ЭНДПОИНТ ====================


@router.post(
    "/public",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Приём заявки с лендинга",
    description=(
        "Публичный эндпоинт без авторизации. Создаёт лид со статусом 'new' "
        "и источником 'landing'. Используется формой на лендинге."
    ),
)
async def create_public_lead(
    data: LeadPublicCreate,
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    """Принять заявку с лендинга и создать лид."""
    lead = await lead_service.create_from_public_request(data)
    return await lead_service.build_lead_response(lead)


# ==================== ЗАЩИЩЁННЫЕ ЭНДПОИНТЫ (admin) ====================


@router.get(
    "",
    response_model=LeadListResponse,
    summary="Список лидов",
    description="Список лидов с фильтрами по статусу и ответственному. "
    "Используется доской канбана.",
)
async def list_leads(
    status_filter: Optional[LeadStatus] = Query(
        default=None,
        alias="status",
        description="Фильтр по статусу воронки",
    ),
    assigned_to: Optional[int] = Query(
        default=None, gt=0, description="Фильтр по ID ответственного админа"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadListResponse:
    """Получить страницу лидов с фильтрами."""
    items, total = await lead_service.list_leads(
        status=status_filter.value if status_filter else None,
        assigned_to=assigned_to,
        limit=limit,
        offset=offset,
    )
    return await lead_service.build_lead_list_response(items, total)


@router.get(
    "/{lead_id}",
    response_model=LeadDetailResponse,
    summary="Карточка лида",
    description="Полная карточка лида вместе с лентой истории активностей.",
)
async def get_lead(
    lead_id: int,
    _admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadDetailResponse:
    """Получить карточку лида с журналом активностей."""
    lead = await lead_service.get_lead_with_activities(lead_id)
    return await lead_service.build_lead_detail_response(lead)


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Правка лида",
    description="Изменение ответственного (assigned_to) и краткой сводки "
    "(notes). Смена статуса - через отдельный эндпоинт /status.",
)
async def update_lead(
    lead_id: int,
    data: LeadUpdate,
    _admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    """Обновить поля лида."""
    lead = await lead_service.update_lead(lead_id, data)
    return await lead_service.build_lead_response(lead)


@router.patch(
    "/{lead_id}/status",
    response_model=LeadResponse,
    summary="Смена статуса лида",
    description="Перемещение лида по воронке. Дописывает системную запись "
    "в журнал. Статус 'lost' требует указания причины.",
)
async def change_lead_status(
    lead_id: int,
    data: LeadStatusUpdate,
    admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    """Сменить статус лида в воронке."""
    lead = await lead_service.change_status(
        lead_id, data, admin_user_id=admin["user_id"]
    )
    return await lead_service.build_lead_response(lead)


@router.post(
    "/{lead_id}/activities",
    response_model=LeadActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить запись в журнал",
    description="Добавление заметки или отметки о звонке в ленту истории "
    "лида. Системные записи (status_changed) так создавать нельзя.",
)
async def add_lead_activity(
    lead_id: int,
    data: LeadActivityCreate,
    admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadActivityResponse:
    """Добавить запись в журнал активностей лида."""
    activity = await lead_service.add_activity(
        lead_id, data, admin_user_id=admin["user_id"]
    )
    return LeadActivityResponse.model_validate(activity)


@router.post(
    "/{lead_id}/convert-to-user",
    response_model=LeadConversionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Конвертировать лид в клиента",
    description=(
        "Создаёт в Auth Service пользователя (без пароля) для лида, "
        "привязывает его к лиду и переводит лид в статус trial_scheduled. "
        "Идемпотентно: повторный вызов не создаёт второго пользователя. "
        "Тело запроса опционально: любое поле, не переданное в body, "
        "будет взято из лида. После слияния обязательны email и studio_id."
    ),
)
async def convert_lead_to_user(
    lead_id: int,
    data: Optional[LeadConvertRequest] = Body(default=None),
    admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadConversionResponse:
    """Конвертировать лид в provisioned-пользователя."""
    return await lead_service.convert_to_user(
        lead_id, admin_user_id=admin["user_id"], data=data,
    )


# ==================== СПРАВОЧНИКИ ====================


@studios_router.get(
    "",
    response_model=List[StudioOption],
    summary="Список активных студий",
    description=(
        "Возвращает все активные студии из локального кеша "
        "(studios_cache, синхронизируется через admin_events). "
        "Используется фронтом для select студии в модалке конвертации лида."
    ),
)
async def list_active_studios(
    _admin: dict = Depends(get_current_admin),
    lead_service: LeadService = Depends(get_lead_service),
) -> List[StudioOption]:
    """Получить список активных студий из локального кеша."""
    studios = await lead_service.studio_cache.get_all_active()
    return [StudioOption.model_validate(s) for s in studios]
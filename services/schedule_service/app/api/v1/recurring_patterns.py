"""
API endpoints шаблонов повторяющихся занятий.

Переписан под модель со слотами. Добавлен POST /preview - сухой прогон,
который считает будущие занятия и находит конфликты, ничего не записывая.
Именно он делает настройку гибкого шаблона безопасной: админ видит точное
число занятий и список проблем до того, как что-то создано.

Обработка доменных ошибок здесь не дублируется. Сервис кидает
RecurringPatternNotFoundException, ClassroomConflictException и прочие,
а превращают их в HTTP-ответы централизованные обработчики в main.py.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import extract_role_name
from app.dependencies import (
    check_studio_access,
    check_teacher_access,
    get_current_teacher,
    get_current_user,
    get_pattern_service,
)
from app.domain.recurrence import calculate_end_time
from app.models.recurring_pattern import RecurringPattern
from app.schemas.common import SuccessResponse
from app.schemas.recurring_pattern import (
    DAY_NAMES,
    PatternGenerationSummary,
    RecurringPatternCreate,
    RecurringPatternListResponse,
    RecurringPatternPreviewRequest,
    RecurringPatternPreviewResponse,
    RecurringPatternResponse,
    RecurringPatternSlotResponse,
    RecurringPatternUpdate,
    RecurringPatternWithGeneration,
)
from app.services.lesson_generator_service import GenerationResult
from app.services.recurring_pattern_service import RecurringPatternService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recurring-patterns", tags=["Recurring Patterns"])


# ==================== СБОРКА ОТВЕТА ====================


def _slot_to_response(slot) -> RecurringPatternSlotResponse:
    """Слот в ответ. end_time считается, в БД его нет."""
    return RecurringPatternSlotResponse(
        id=slot.id,
        day_of_week=slot.day_of_week,
        day_name=DAY_NAMES[slot.day_of_week],
        start_time=slot.start_time,
        end_time=calculate_end_time(slot.start_time, slot.duration_minutes),
        duration_minutes=slot.duration_minutes,
        classroom_id=slot.classroom_id,
    )


async def _build_response(
    pattern_id: int,
    pattern_service: RecurringPatternService,
) -> RecurringPatternResponse:
    """
    Собрать ответ по шаблону.

    Шаблон перечитывается из БД, а не берётся из переданного объекта.
    Причина в replace_slots: он удаляет слоты запросом и создаёт новые,
    поэтому коллекция pattern.slots в памяти после него описывает уже
    несуществующее состояние. Чтение внутри той же транзакции видит
    актуальные данные и стоит один запрос.
    """
    pattern = await pattern_service.get_pattern(pattern_id)

    student_ids = await pattern_service.get_pattern_student_ids(pattern.id)
    generated_count = await pattern_service.count_generated_lessons(pattern.id)

    return RecurringPatternResponse(
        id=pattern.id,
        studio_id=pattern.studio_id,
        teacher_id=pattern.teacher_id,
        valid_from=pattern.valid_from,
        valid_until=pattern.valid_until,
        anchor_date=pattern.anchor_date,
        week_interval=pattern.week_interval,
        is_active=pattern.is_active,
        notes=pattern.notes,
        created_at=pattern.created_at,
        updated_at=pattern.updated_at,
        slots=[
            _slot_to_response(slot)
            for slot in sorted(
                pattern.slots, key=lambda s: (s.day_of_week, s.start_time)
            )
        ],
        student_ids=student_ids,
        generated_lessons_count=generated_count,
    )


def _generation_summary(
    result: GenerationResult,
    pattern_service: RecurringPatternService,
) -> PatternGenerationSummary:
    """Результат генерации в схему ответа."""
    return PatternGenerationSummary(
        created_count=result.created_count,
        already_existed_count=result.already_existed_count,
        blocked_count=result.blocked_count,
        batch_id=str(result.batch_id) if result.batch_id else None,
        conflicts=pattern_service.conflicts_to_items(result.blocked),
    )


def _assert_can_manage(current_user: dict, studio_id: int, teacher_id: int) -> None:
    """
    Права на управление шаблоном.

    Админ - в своей студии для любого преподавателя.
    Преподаватель - только для себя.
    """
    if not check_studio_access(current_user, studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой студии!",
        )

    role = extract_role_name(current_user.get("role"))
    if role != "admin" and current_user.get("user_id") != teacher_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете управлять только своими шаблонами!",
        )


# ==================== ПРЕДПРОСМОТР ====================


@router.post(
    "/preview",
    response_model=RecurringPatternPreviewResponse,
    summary="Предпросмотр: что получится при сохранении",
)
async def preview_recurring_pattern(
    data: RecurringPatternPreviewRequest,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Посчитать занятия и конфликты, ничего не создавая.

    В БД не записывается ничего. Числа считаются тем же кодом, что и
    настоящая генерация, поэтому will_create_count совпадёт с тем,
    сколько занятий появится после сохранения.
    """
    _assert_can_manage(current_user, data.studio_id, data.teacher_id)

    plan = await pattern_service.preview(data)

    return RecurringPatternPreviewResponse(
        will_create_count=plan.will_create_count,
        already_exists_count=plan.already_exists_count,
        blocked_count=plan.blocked_count,
        horizon_end=plan.horizon_end,
        dates=[item.lesson_date for item in plan.to_create],
        conflicts=pattern_service.conflicts_to_items(plan.blocked),
    )


# ==================== СОЗДАНИЕ ====================


@router.post(
    "",
    response_model=RecurringPatternWithGeneration,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон",
)
async def create_recurring_pattern(
    data: RecurringPatternCreate,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Создать шаблон и сгенерировать занятия на горизонт.

    Ответ содержит и шаблон, и итог генерации: сколько создано, сколько
    заблокировано конфликтами и по какой причине. batch_id пригодится,
    если понадобится откатить прогон.
    """
    _assert_can_manage(current_user, data.studio_id, data.teacher_id)

    pattern, result = await pattern_service.create_pattern(data)

    return RecurringPatternWithGeneration(
        pattern=await _build_response(pattern.id, pattern_service),
        generation=_generation_summary(result, pattern_service),
    )


# ==================== ЧТЕНИЕ ====================


@router.get(
    "",
    response_model=RecurringPatternListResponse,
    summary="Список шаблонов",
)
async def get_recurring_patterns(
    studio_id: Optional[int] = Query(None, description="Фильтр по студии"),
    teacher_id: Optional[int] = Query(None, description="Фильтр по преподавателю"),
    active_only: bool = Query(True, description="Только активные"),
    current_user: dict = Depends(get_current_user),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """Шаблоны с фильтрами. Ученикам недоступно."""
    role = extract_role_name(current_user.get("role"))
    user_id = current_user.get("user_id")

    if role == "admin":
        if teacher_id:
            patterns = await pattern_service.get_patterns_by_teacher(
                teacher_id, active_only
            )
        elif studio_id:
            patterns = await pattern_service.get_patterns_by_studio(
                studio_id, active_only
            )
        else:
            patterns = []
    elif role == "teacher":
        patterns = await pattern_service.get_patterns_by_teacher(
            user_id, active_only
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к шаблонам!",
        )

    # Каждый шаблон дочитывается полностью внутри _build_response.
    # Шаблонов на студию десятки, не тысячи.
    response_patterns = []
    for item in patterns:
        response_patterns.append(await _build_response(item.id, pattern_service))

    return RecurringPatternListResponse(
        patterns=response_patterns,
        total=len(response_patterns),
    )


@router.get(
    "/{pattern_id}",
    response_model=RecurringPatternResponse,
    summary="Шаблон по ID",
)
async def get_recurring_pattern(
    pattern_id: int,
    current_user: dict = Depends(get_current_user),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    pattern = await pattern_service.get_pattern(pattern_id)

    if not check_teacher_access(current_user, pattern.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этому шаблону!",
        )

    return await _build_response(pattern.id, pattern_service)


# ==================== ОБНОВЛЕНИЕ ====================


@router.patch(
    "/{pattern_id}",
    response_model=RecurringPatternWithGeneration,
    summary="Обновить шаблон",
)
async def update_recurring_pattern(
    pattern_id: int,
    data: RecurringPatternUpdate,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Обновить шаблон.

    Если менялись слоты, период действия или периодичность, будущие
    занятия пересобираются. Прошлые занятия, проведённые и изменённые
    вручную не затрагиваются.
    """
    pattern = await pattern_service.get_pattern(pattern_id)
    _assert_can_manage(current_user, pattern.studio_id, pattern.teacher_id)

    updated, result = await pattern_service.update_pattern(pattern_id, data)

    return RecurringPatternWithGeneration(
        pattern=await _build_response(updated.id, pattern_service),
        generation=_generation_summary(result, pattern_service),
    )


@router.post(
    "/{pattern_id}/deactivate",
    response_model=RecurringPatternResponse,
    summary="Выключить шаблон",
)
async def deactivate_recurring_pattern(
    pattern_id: int,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Выключить шаблон, сохранив уже созданные занятия.

    Штатный способ прекратить регулярные занятия: расписание доживает
    до конца горизонта и дальше не продлевается.
    """
    pattern = await pattern_service.get_pattern(pattern_id)
    _assert_can_manage(current_user, pattern.studio_id, pattern.teacher_id)

    updated = await pattern_service.deactivate_pattern(pattern_id)
    return await _build_response(updated.id, pattern_service)


# ==================== УДАЛЕНИЕ ====================


@router.delete(
    "/{pattern_id}",
    response_model=SuccessResponse,
    summary="Удалить шаблон",
)
async def delete_recurring_pattern(
    pattern_id: int,
    delete_future_lessons: bool = Query(
        False,
        description="Удалить будущие занятия шаблона",
    ),
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Удалить шаблон.

    По умолчанию занятия остаются в расписании и просто теряют связь
    с шаблоном. С delete_future_lessons=true дополнительно удаляются
    будущие занятия - но только те, что не проводились и не правились
    вручную. Прошлое не удаляется ни при каких условиях.
    """
    pattern = await pattern_service.get_pattern(pattern_id)
    _assert_can_manage(current_user, pattern.studio_id, pattern.teacher_id)

    deleted = await pattern_service.delete_pattern(
        pattern_id, delete_future_lessons=delete_future_lessons
    )

    message = f"Шаблон {pattern_id} удалён"
    if deleted:
        message += f", вместе с ним удалено занятий: {deleted}"

    return SuccessResponse(success=True, message=message)
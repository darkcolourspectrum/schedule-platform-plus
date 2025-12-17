"""
API endpoints для Recurring Patterns (шаблоны повторяющихся занятий)
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.schemas.recurring_pattern import (
    RecurringPatternCreate,
    RecurringPatternUpdate,
    RecurringPatternResponse,
    RecurringPatternListResponse
)
from app.schemas.common import SuccessResponse
from app.services.recurring_pattern_service import RecurringPatternService
from app.dependencies import (
    get_current_user,
    get_current_teacher,
    get_pattern_service,
    check_studio_access,
    check_teacher_access
)
from app.core.security import extract_role_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recurring-patterns", tags=["Recurring Patterns"])


@router.post(
    "",
    response_model=RecurringPatternResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон повторяющегося занятия"
)
async def create_recurring_pattern(
    data: RecurringPatternCreate,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service)
):
    """
    Создать шаблон повторяющегося занятия
    
    Автоматически генерирует занятия на ближайшие 2 недели
    """
    # Проверяем доступ к студии
    if not check_studio_access(current_user, data.studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this studio"
        )
    
    # Проверяем что преподаватель создает шаблон для себя (если не админ)
    role = extract_role_name(current_user.get("role"))
    if role != "admin" and current_user.get("id") != data.teacher_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create patterns for yourself"
        )
    
    pattern, generated_count = await pattern_service.create_pattern(data)
    
    # Формируем ответ
    student_ids = await pattern_service.get_pattern_student_ids(pattern.id)
    
    response = RecurringPatternResponse.model_validate(pattern)
    response.student_ids = student_ids
    response.generated_lessons_count = generated_count
    
    return response


@router.get(
    "",
    response_model=RecurringPatternListResponse,
    summary="Получить список шаблонов"
)
async def get_recurring_patterns(
    studio_id: int = Query(None, description="Фильтр по студии"),
    teacher_id: int = Query(None, description="Фильтр по преподавателю"),
    active_only: bool = Query(True, description="Только активные"),
    current_user: dict = Depends(get_current_user),
    pattern_service: RecurringPatternService = Depends(get_pattern_service)
):
    """Получить список шаблонов с фильтрами"""
    
    # Определяем фильтры на основе роли
    role = extract_role_name(current_user.get("role"))
    user_id = current_user.get("id")
    
    if role == "admin":
        # Админ может фильтровать как угодно
        if teacher_id:
            patterns = await pattern_service.get_patterns_by_teacher(teacher_id, active_only)
        elif studio_id:
            patterns = await pattern_service.get_patterns_by_studio(studio_id, active_only)
        else:
            # Все шаблоны (пока не реализовано)
            patterns = []
    
    elif role == "teacher":
        # Преподаватель видит только свои шаблоны
        patterns = await pattern_service.get_patterns_by_teacher(user_id, active_only)
    
    else:
        # Ученики не имеют доступа к шаблонам
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students cannot access recurring patterns"
        )
    
    # Обогащаем данные
    response_patterns = []
    for pattern in patterns:
        student_ids = await pattern_service.get_pattern_student_ids(pattern.id)
        generated_count = await pattern_service.count_generated_lessons(pattern.id)
        
        pattern_response = RecurringPatternResponse.model_validate(pattern)
        pattern_response.student_ids = student_ids
        pattern_response.generated_lessons_count = generated_count
        
        response_patterns.append(pattern_response)
    
    return RecurringPatternListResponse(
        patterns=response_patterns,
        total=len(response_patterns)
    )


@router.get(
    "/{pattern_id}",
    response_model=RecurringPatternResponse,
    summary="Получить шаблон по ID"
)
async def get_recurring_pattern(
    pattern_id: int,
    current_user: dict = Depends(get_current_user),
    pattern_service: RecurringPatternService = Depends(get_pattern_service)
):
    """Получить шаблон повторяющегося занятия по ID"""
    
    pattern = await pattern_service.get_pattern(pattern_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, pattern.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this pattern"
        )
    
    student_ids = await pattern_service.get_pattern_student_ids(pattern.id)
    generated_count = await pattern_service.count_generated_lessons(pattern.id)
    
    response = RecurringPatternResponse.model_validate(pattern)
    response.student_ids = student_ids
    response.generated_lessons_count = generated_count
    
    return response


@router.patch(
    "/{pattern_id}",
    response_model=RecurringPatternResponse,
    summary="Обновить шаблон"
)
async def update_recurring_pattern(
    pattern_id: int,
    data: RecurringPatternUpdate,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service)
):
    """
    Обновить шаблон повторяющегося занятия
    
    Примечание: Уже созданные занятия не изменяются
    """
    
    pattern = await pattern_service.get_pattern(pattern_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, pattern.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this pattern"
        )
    
    updated_pattern = await pattern_service.update_pattern(pattern_id, data)
    
    student_ids = await pattern_service.get_pattern_student_ids(pattern_id)
    generated_count = await pattern_service.count_generated_lessons(pattern_id)
    
    response = RecurringPatternResponse.model_validate(updated_pattern)
    response.student_ids = student_ids
    response.generated_lessons_count = generated_count
    
    return response


@router.delete(
    "/{pattern_id}",
    response_model=SuccessResponse,
    summary="Удалить шаблон"
)
async def delete_recurring_pattern(
    pattern_id: int,
    current_user: dict = Depends(get_current_teacher),
    pattern_service: RecurringPatternService = Depends(get_pattern_service)
):
    """
    Удалить шаблон повторяющегося занятия
    
    Уже созданные занятия остаются (recurring_pattern_id становится NULL)
    """
    
    pattern = await pattern_service.get_pattern(pattern_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, pattern.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this pattern"
        )
    
    await pattern_service.delete_pattern(pattern_id)
    
    return SuccessResponse(
        success=True,
        message=f"Recurring pattern {pattern_id} deleted successfully"
    )

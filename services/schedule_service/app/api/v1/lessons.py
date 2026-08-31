"""
API endpoints занятий.

Главное изменение - ответы больше не врут. Раньше каждый эндпоинт
собирал список учеников с захардкоженным статусом посещения:

    LessonStudentInfo(student_id=sid, attendance_status="attended")

В базе при этом лежало 'scheduled'. Теперь статус читается оттуда,
где он есть на самом деле.

Добавлен POST /{id}/restore - возврат отменённого занятия в расписание
с проверкой конфликтов. Переход cancelled -> scheduled был разрешён
таблицей статусов, но не имел ни эндпоинта, ни проверки.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import extract_role_name
from app.dependencies import (
    check_studio_access,
    check_teacher_access,
    get_current_teacher,
    get_current_user,
    get_lesson_service,
)
from app.models.lesson import Lesson
from app.schemas.common import SuccessResponse
from app.schemas.lesson import (
    LessonCancelRequest,
    LessonCompleteRequest,
    LessonCreate,
    LessonResponse,
    LessonStudentInfo,
    LessonUpdate,
)
from app.services.lesson_service import LessonService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["Lessons"])


async def _build_response(
    lesson: Lesson,
    lesson_service: LessonService,
) -> LessonResponse:
    """
    Собрать ответ с настоящей посещаемостью.

    Один общий сборщик на все эндпоинты: раньше каждый собирал ответ
    сам и подставлял статус посещения из головы, поэтому они расходились
    между собой и с базой.
    """
    students = await lesson_service.get_lesson_students(lesson.id)

    response = LessonResponse.model_validate(lesson)
    response.students = [
        LessonStudentInfo(
            student_id=item.student_id,
            attendance_status=item.attendance_status,
        )
        for item in students
    ]
    response.is_recurring = lesson.recurring_pattern_id is not None
    return response


def _assert_lesson_access(current_user: dict, teacher_id: int) -> None:
    if not check_teacher_access(current_user, teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этому занятию",
        )


# ==================== СОЗДАНИЕ ====================


@router.post(
    "",
    response_model=LessonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать разовое занятие",
)
async def create_lesson(
    data: LessonCreate,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Создать разовое занятие.

    Проверяются конфликты по кабинету, преподавателю и ученикам.
    При конфликте возвращается 409 с указанием причины.
    """
    if not check_studio_access(current_user, data.studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой студии",
        )

    role = extract_role_name(current_user.get("role"))
    if role != "admin" and current_user.get("user_id") != data.teacher_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете создавать занятия только для себя",
        )

    lesson = await lesson_service.create_lesson(data)
    return await _build_response(lesson, lesson_service)


# ==================== ЧТЕНИЕ ====================


@router.get(
    "/{lesson_id}",
    response_model=LessonResponse,
    summary="Занятие по ID",
)
async def get_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    lesson = await lesson_service.get_lesson(lesson_id)

    role = extract_role_name(current_user.get("role"))
    user_id = current_user.get("user_id")

    if role == "student":
        student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
        if user_id not in student_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="У вас нет доступа к этому занятию",
            )
    else:
        _assert_lesson_access(current_user, lesson.teacher_id)

    return await _build_response(lesson, lesson_service)


# ==================== ИЗМЕНЕНИЕ ====================


@router.patch(
    "/{lesson_id}",
    response_model=LessonResponse,
    summary="Обновить занятие",
)
async def update_lesson(
    lesson_id: int,
    data: LessonUpdate,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Изменить дату, время, кабинет или заметки.

    Занятие, изменённое здесь, помечается как правленное вручную:
    последующая перегенерация из шаблона его не тронет.
    """
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    updated = await lesson_service.update_lesson(lesson_id, data)
    return await _build_response(updated, lesson_service)


# ==================== СТАТУСЫ ====================


@router.post(
    "/{lesson_id}/cancel",
    response_model=LessonResponse,
    summary="Отменить занятие",
)
async def cancel_lesson(
    lesson_id: int,
    data: LessonCancelRequest | None = None,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Отменить занятие. Кабинет и время освобождаются."""
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    reason = data.reason if data else None
    cancelled = await lesson_service.cancel_lesson(lesson_id, reason)
    return await _build_response(cancelled, lesson_service)


@router.post(
    "/{lesson_id}/restore",
    response_model=LessonResponse,
    summary="Вернуть отменённое занятие",
)
async def restore_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Вернуть занятие в расписание.

    Пока занятие было отменено, его время считалось свободным. Поэтому
    восстановление проверяет конфликты заново и вернёт 409, если слот
    успели занять.
    """
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    restored = await lesson_service.restore_lesson(lesson_id)
    return await _build_response(restored, lesson_service)


@router.post(
    "/{lesson_id}/complete",
    response_model=LessonResponse,
    summary="Отметить занятие проведённым",
)
async def complete_lesson(
    lesson_id: int,
    data: LessonCompleteRequest | None = None,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Отметить занятие проведённым.

    Можно передать посещаемость по ученикам. Без неё все считаются
    присутствовавшими.
    """
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    attendance = data.attendance if data else None
    completed = await lesson_service.complete_lesson(lesson_id, attendance)
    return await _build_response(completed, lesson_service)


@router.post(
    "/{lesson_id}/mark-missed",
    response_model=LessonResponse,
    summary="Отметить занятие пропущенным",
)
async def mark_lesson_missed(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Занятие не состоялось по вине ученика."""
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    missed = await lesson_service.mark_as_missed(lesson_id)
    return await _build_response(missed, lesson_service)


# ==================== УДАЛЕНИЕ ====================


@router.delete(
    "/{lesson_id}",
    response_model=SuccessResponse,
    summary="Удалить занятие",
)
async def delete_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Удалить занятие.

    Доступно только для запланированных занятий в будущем. Проведённые,
    пропущенные и прошедшие занятия удалить нельзя - для них правильное
    действие отмена.
    """
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    await lesson_service.delete_lesson(lesson_id)

    return SuccessResponse(
        success=True,
        message=f"Занятие {lesson_id} удалено",
    )
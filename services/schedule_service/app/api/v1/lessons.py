"""
API endpoints для Lessons (занятия)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.lesson import (
    LessonCreate,
    LessonUpdate,
    LessonResponse,
    LessonStudentInfo
)
from app.schemas.common import SuccessResponse
from app.services.lesson_service import LessonService
from app.dependencies import (
    get_current_user,
    get_current_teacher,
    get_lesson_service,
    check_studio_access,
    check_teacher_access
)
from app.core.security import extract_role_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["Lessons"])


@router.post(
    "",
    response_model=LessonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать разовое занятие"
)
async def create_lesson(
    data: LessonCreate,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Создать разовое занятие
    
    Проверяет конфликты кабинета перед созданием
    """
    # Проверяем доступ к студии
    if not check_studio_access(current_user, data.studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this studio"
        )
    
    # Проверяем что преподаватель создает занятие для себя (если не админ)
    role = extract_role_name(current_user.get("role"))
    if role != "admin" and current_user.get("id") != data.teacher_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create lessons for yourself"
        )
    
    lesson = await lesson_service.create_lesson(data)
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson.id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="scheduled")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(lesson)
    response.students = students
    response.is_recurring = False
    
    return response


@router.get(
    "/{lesson_id}",
    response_model=LessonResponse,
    summary="Получить занятие по ID"
)
async def get_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_user),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """Получить информацию о занятии"""
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    role = extract_role_name(current_user.get("role"))
    user_id = current_user.get("id")
    
    # Админ видит всё
    if role == "admin":
        pass
    # Преподаватель видит свои занятия
    elif role == "teacher" and lesson.teacher_id == user_id:
        pass
    # Ученик видит свои занятия
    elif role == "student":
        student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
        if user_id not in student_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this lesson"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson.id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="scheduled")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(lesson)
    response.students = students
    response.is_recurring = lesson.recurring_pattern_id is not None
    
    return response


@router.patch(
    "/{lesson_id}",
    response_model=LessonResponse,
    summary="Обновить занятие"
)
async def update_lesson(
    lesson_id: int,
    data: LessonUpdate,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Обновить занятие
    
    Можно изменить: кабинет, время, статус, заметки
    """
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, lesson.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    updated_lesson = await lesson_service.update_lesson(lesson_id, data)
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="scheduled")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(updated_lesson)
    response.students = students
    response.is_recurring = updated_lesson.recurring_pattern_id is not None
    
    return response


@router.post(
    "/{lesson_id}/cancel",
    response_model=LessonResponse,
    summary="Отменить занятие"
)
async def cancel_lesson(
    lesson_id: int,
    reason: str = None,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """Отменить занятие"""
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, lesson.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    cancelled_lesson = await lesson_service.cancel_lesson(lesson_id, reason)
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="cancelled")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(cancelled_lesson)
    response.students = students
    response.is_recurring = cancelled_lesson.recurring_pattern_id is not None
    
    return response


@router.post(
    "/{lesson_id}/complete",
    response_model=LessonResponse,
    summary="Отметить занятие как завершенное"
)
async def complete_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """Отметить занятие как завершенное"""
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, lesson.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    completed_lesson = await lesson_service.complete_lesson(lesson_id)
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="attended")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(completed_lesson)
    response.students = students
    response.is_recurring = completed_lesson.recurring_pattern_id is not None
    
    return response


@router.post(
    "/{lesson_id}/mark-missed",
    response_model=LessonResponse,
    summary="Отметить занятие как пропущенное"
)
async def mark_lesson_missed(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """Отметить занятие как пропущенное учеником"""
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, lesson.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    missed_lesson = await lesson_service.mark_as_missed(lesson_id)
    
    # Формируем ответ
    student_ids = await lesson_service.get_lesson_student_ids(lesson_id)
    students = [
        LessonStudentInfo(student_id=sid, attendance_status="missed")
        for sid in student_ids
    ]
    
    response = LessonResponse.model_validate(missed_lesson)
    response.students = students
    response.is_recurring = missed_lesson.recurring_pattern_id is not None
    
    return response


@router.delete(
    "/{lesson_id}",
    response_model=SuccessResponse,
    summary="Удалить занятие"
)
async def delete_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """Удалить занятие"""
    
    lesson = await lesson_service.get_lesson(lesson_id)
    
    # Проверяем доступ
    if not check_teacher_access(current_user, lesson.teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this lesson"
        )
    
    await lesson_service.delete_lesson(lesson_id)
    
    return SuccessResponse(
        success=True,
        message=f"Lesson {lesson_id} deleted successfully"
    )

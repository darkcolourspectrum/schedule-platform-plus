"""
API endpoints для Schedule (расписание)
"""

import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.schemas.schedule import (
    StudioScheduleResponse,
    TeacherScheduleResponse,
    StudentScheduleResponse,
    GenerateLessonsRequest,
    GenerateLessonsResponse,
    ConflictCheckRequest,
    ConflictCheckResponse
)
from app.services.schedule_service import ScheduleService
from app.services.lesson_generator_service import LessonGeneratorService
from app.services.lesson_service import LessonService
from app.dependencies import (
    get_current_user,
    get_current_admin,
    get_schedule_service,
    get_generator_service,
    get_lesson_service,
    check_studio_access,
    check_teacher_access,
    check_student_access
)
from app.core.security import extract_role_name
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["Schedule"])


@router.get(
    "/studios/{studio_id}",
    response_model=StudioScheduleResponse,
    summary="Получить расписание студии"
)
async def get_studio_schedule(
    studio_id: int,
    from_date: date = Query(..., description="Начальная дата"),
    to_date: date = Query(..., description="Конечная дата"),
    current_user: dict = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """
    Получить расписание студии за период
    
    Доступно: admin, teacher (своей студии)
    """
    # Проверяем доступ к студии
    if not check_studio_access(current_user, studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this studio"
        )
    
    # Получаем расписание
    lessons = await schedule_service.get_studio_schedule(studio_id, from_date, to_date)
    
    # TODO: Получить название студии из Admin Service
    studio_name = f"Studio {studio_id}"
    
    return StudioScheduleResponse(
        studio_id=studio_id,
        studio_name=studio_name,
        from_date=from_date,
        to_date=to_date,
        lessons=lessons,
        total=len(lessons)
    )


@router.get(
    "/teachers/{teacher_id}",
    response_model=TeacherScheduleResponse,
    summary="Получить расписание преподавателя"
)
async def get_teacher_schedule(
    teacher_id: int,
    from_date: date = Query(..., description="Начальная дата"),
    to_date: date = Query(..., description="Конечная дата"),
    current_user: dict = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """
    Получить расписание преподавателя за период
    
    Доступно: admin, teacher (свое расписание)
    """
    # Проверяем доступ
    if not check_teacher_access(current_user, teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this teacher's schedule"
        )
    
    # Получаем расписание
    lessons = await schedule_service.get_teacher_schedule(teacher_id, from_date, to_date)
    
    # TODO: Получить имя преподавателя
    teacher_name = f"Teacher {teacher_id}"
    
    return TeacherScheduleResponse(
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        from_date=from_date,
        to_date=to_date,
        lessons=lessons,
        total=len(lessons)
    )


@router.get(
    "/students/{student_id}",
    response_model=StudentScheduleResponse,
    summary="Получить занятия ученика"
)
async def get_student_schedule(
    student_id: int,
    from_date: date = Query(..., description="Начальная дата"),
    to_date: date = Query(..., description="Конечная дата"),
    current_user: dict = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """
    Получить занятия ученика за период
    
    Доступно: admin, teacher (той же студии), student (свои занятия)
    """
    # Проверяем доступ
    if not check_student_access(current_user, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this student's schedule"
        )
    
    # Получаем расписание
    lessons = await schedule_service.get_student_schedule(student_id, from_date, to_date)
    
    # TODO: Получить имя ученика
    student_name = f"Student {student_id}"
    
    return StudentScheduleResponse(
        student_id=student_id,
        student_name=student_name,
        from_date=from_date,
        to_date=to_date,
        lessons=lessons,
        total=len(lessons)
    )


@router.post(
    "/generate",
    response_model=GenerateLessonsResponse,
    summary="Генерация занятий"
)
async def generate_lessons(
    request: GenerateLessonsRequest,
    current_user: dict = Depends(get_current_admin),
    generator_service: LessonGeneratorService = Depends(get_generator_service)
):
    """
    Ручная генерация занятий из шаблонов
    
    Доступно только админам
    """
    
    until_date = request.until_date or (
        date.today() + timedelta(weeks=settings.schedule_generation_weeks)
    )
    
    if request.pattern_id:
        # Генерация для конкретного шаблона
        from app.dependencies import get_pattern_service
        from app.repositories.recurring_pattern_repository import RecurringPatternRepository
        from app.database.connection import get_schedule_db
        
        # Это упрощенный вариант, в production лучше через dependency
        async for db in get_schedule_db():
            pattern_repo = RecurringPatternRepository(db)
            pattern = await pattern_repo.get_by_id(request.pattern_id)
            
            if not pattern:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Pattern {request.pattern_id} not found"
                )
            
            generated, skipped, errors = await generator_service.generate_lessons_for_pattern(
                pattern,
                until_date
            )
            break
    else:
        # Генерация для всех шаблонов
        generated, skipped, errors = await generator_service.generate_all_patterns(until_date)
    
    return GenerateLessonsResponse(
        success=True,
        generated_count=generated,
        skipped_count=skipped,
        errors=errors,
        message=f"Generated {generated} lessons, skipped {skipped}"
    )


@router.post(
    "/check-conflict",
    response_model=ConflictCheckResponse,
    summary="Проверка конфликта кабинета"
)
async def check_classroom_conflict(
    request: ConflictCheckRequest,
    current_user: dict = Depends(get_current_user),
    lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Проверить конфликт кабинета на определенную дату и время
    
    Полезно для валидации перед созданием занятия
    """
    
    has_conflict = await lesson_service.check_classroom_conflict(
        classroom_id=request.classroom_id,
        lesson_date=request.lesson_date,
        start_time=request.start_time,
        end_time=request.end_time,
        exclude_lesson_id=request.exclude_lesson_id
    )
    
    conflicting_lessons = []
    
    if has_conflict:
        # Получаем конфликтующие занятия для деталей
        from app.repositories.lesson_repository import LessonRepository
        from app.database.connection import get_schedule_db
        
        async for db in get_schedule_db():
            lesson_repo = LessonRepository(db)
            lessons = await lesson_repo.get_by_classroom(
                request.classroom_id,
                request.lesson_date,
                request.exclude_lesson_id
            )
            
            for lesson in lessons:
                # Проверяем пересечение
                if (request.start_time < lesson.end_time and 
                    request.end_time > lesson.start_time):
                    conflicting_lessons.append({
                        "lesson_id": lesson.id,
                        "start_time": str(lesson.start_time),
                        "end_time": str(lesson.end_time),
                        "teacher_id": lesson.teacher_id
                    })
            break
    
    return ConflictCheckResponse(
        has_conflict=has_conflict,
        conflicting_lessons=conflicting_lessons
    )

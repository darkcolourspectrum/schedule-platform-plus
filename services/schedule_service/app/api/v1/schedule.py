"""
API endpoints для Schedule (расписание)
"""

import logging
from datetime import date
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
from app.services.recurring_pattern_service import RecurringPatternService
from app.services.schedule_service import ScheduleService
from app.services.lesson_generator_service import LessonGeneratorService
from app.services.lesson_service import LessonService
from app.services.conflict_service import ConflictService
from app.domain.conflicts import LessonCandidate
from app.dependencies import (
    get_current_user,
    get_current_admin,
    get_schedule_service,
    get_generator_service,
    get_lesson_service,
    check_studio_access,
    check_teacher_access,
    check_student_access,
    get_pattern_service,
     get_conflict_service,
)
from app.core.security import extract_role_name

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
    summary="Генерация занятий для шаблона"
)
async def generate_lessons(
    request: GenerateLessonsRequest,
    current_user: dict = Depends(get_current_admin),
    generator_service: LessonGeneratorService = Depends(get_generator_service),
    pattern_service: RecurringPatternService = Depends(get_pattern_service),
):
    """
    Ручная догенерация занятий для одного шаблона.

    Идемпотентна: повторный вызов на тех же данных создаст ноль занятий,
    потому что все целевые даты уже будут заняты.

    Массовая генерация по всем шаблонам сюда не входит - её выполняет
    фоновый воркер. Раньше она запускалась из этого эндпоинта и из GET
    расписания студии, что и было источником дублей.

    Доступно только админам.
    """
    if not request.pattern_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Укажите pattern_id. Массовая генерация выполняется "
                "фоновым воркером, а не этим эндпоинтом"
            ),
        )

    pattern = await pattern_service.get_pattern(request.pattern_id)

    result = await generator_service.generate_pattern(
        pattern=pattern,
        slots=list(pattern.slots),
        student_ids=await pattern_service.get_pattern_student_ids(pattern.id),
        until_date=request.until_date,
    )

    return GenerateLessonsResponse(
        success=True,
        generated_count=result.created_count,
        skipped_count=result.blocked_count + result.already_existed_count,
        errors=[],
        message=(
            f"Создано {result.created_count}, "
            f"уже существовало {result.already_existed_count}, "
            f"заблокировано конфликтами {result.blocked_count}"
        ),
    )


@router.post(
    "/check-conflict",
    response_model=ConflictCheckResponse,
    summary="Проверка конфликтов перед созданием занятия"
)
async def check_classroom_conflict(
    request: ConflictCheckRequest,
    current_user: dict = Depends(get_current_user),
    conflict_service: ConflictService = Depends(get_conflict_service),
):
    """
    Проверить, свободно ли время.

    Проверяются три ресурса, а не один: кабинет, преподаватель и ученики.
    Раньше проверялся только кабинет, поэтому преподавателя можно было
    поставить в два места одновременно.

    Ответ носит справочный характер. Настоящая защита стоит в базе -
    два EXCLUDE-констрейнта на lessons, которые не обойти даже двум
    одновременным запросам.
    """
    candidate = LessonCandidate(
        lesson_date=request.lesson_date,
        start_time=request.start_time,
        end_time=request.end_time,
        teacher_id=current_user.get("user_id"),
        classroom_id=request.classroom_id,
    )

    report = await conflict_service.check_single(
        candidate, exclude_lesson_id=request.exclude_lesson_id
    )

    return ConflictCheckResponse(
        has_conflict=report.has_conflicts,
        conflicting_lessons=[
            {
                "lesson_id": c.existing_lesson_id,
                "kind": c.kind.value,
                "start_time": str(c.other_start),
                "end_time": str(c.other_end),
                "subject_id": c.subject_id,
            }
            for c in report.conflicts
        ],
    )

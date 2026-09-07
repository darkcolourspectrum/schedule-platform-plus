"""
API занятий.

Два сборщика ответа. _build_response отдаёт занятие с настоящей
посещаемостью и используется всюду, где ответ нужен для обновления
состояния после действия. _build_details_response добавляет имена
преподавателя, учеников, кабинета и студии - он один и обслуживает
карточку занятия.

Оба перечисляют поля явно, а не через model_validate. Валидация прямо
с ORM-объекта из-за from_attributes лезет читать связь lesson.students,
а это ленивая загрузка: синхронный поход в базу посреди асинхронного
кода, на котором SQLAlchemy падает с MissingGreenlet.

Права разведены по ролям: читать занятие может ученик из его состава,
менять - только преподаватель занятия или админ студии.
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
    get_schedule_service,
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
    LessonWithDetails,
)
from app.services.lesson_service import LessonService
from app.services.schedule_service import ScheduleService
from app.domain.recurrence import lesson_has_ended


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["Lessons"])


async def _build_response(
    lesson: Lesson,
    lesson_service: LessonService,
) -> LessonResponse:
    """
    Собрать ответ с настоящей посещаемостью.

    Поля перечислены явно, а не через model_validate. Валидация прямо
    с ORM-объекта из-за from_attributes пытается прочитать связь
    lesson.students, а это ленивая загрузка: синхронный поход в базу
    посреди асинхронного кода, на котором SQLAlchemy падает
    с MissingGreenlet. Ученики приходят отдельным запросом ниже.

    Один общий сборщик на все эндпоинты: раньше каждый собирал ответ
    сам и подставлял статус посещения из головы, поэтому они расходились
    между собой и с базой.
    """
    students = await lesson_service.get_lesson_students(lesson.id)

    return LessonResponse(
        id=lesson.id,
        studio_id=lesson.studio_id,
        teacher_id=lesson.teacher_id,
        classroom_id=lesson.classroom_id,
        recurring_pattern_id=lesson.recurring_pattern_id,
        lesson_date=lesson.lesson_date,
        start_time=lesson.start_time,
        end_time=lesson.end_time,
        status=lesson.status,
        notes=lesson.notes,
        cancellation_reason=lesson.cancellation_reason,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        students=[
            LessonStudentInfo(
                student_id=item.student_id,
                attendance_status=item.attendance_status,
            )
            for item in students
        ],
        is_recurring=lesson.recurring_pattern_id is not None,
        has_ended=lesson_has_ended(lesson.lesson_date, lesson.end_time),
    )

async def _build_details_response(
    lesson: Lesson,
    lesson_service: LessonService,
    schedule_service: ScheduleService,
) -> LessonWithDetails:
    """
    Ответ для карточки занятия: посещаемость плюс имена.


    Раньше ни один источник не был самодостаточен. Список расписания
    отдавал имена без посещаемости, а GET занятия - посещаемость без
    единого имени, только id. Карточку приходилось бы сшивать на фронте
    из двух ответов, и работала бы она только там, откуда открыта.
    """
    base = await _build_response(lesson, lesson_service)
    names = await schedule_service.get_lesson_names(lesson)

    response = LessonWithDetails(
        **base.model_dump(),
        teacher_name=names["teacher_name"],
        classroom_name=names["classroom_name"],
        studio_name=names["studio_name"],
    )

    for item in response.students:
        item.student_name = names["student_names"].get(item.student_id)

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
    response_model=LessonWithDetails,
    summary="Занятие по ID",
)
async def get_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_user),
    lesson_service: LessonService = Depends(get_lesson_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """
    Занятие со всем, что нужно карточке: посещаемость и имена.

    Единственный эндпоинт, отдающий имена. Остальные возвращают
    LessonResponse: там ответ нужен для обновления состояния после
    действия, а не для показа человеку.
    """
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

    return await _build_details_response(
        lesson, lesson_service, schedule_service
    )


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

@router.post(
    "/{lesson_id}/mark-teacher-missed",
    response_model=LessonResponse,
    summary="Занятие не состоялось по вине преподавателя",
)
async def mark_lesson_teacher_missed(
    lesson_id: int,
    current_user: dict = Depends(get_current_teacher),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """
    Отметить, что занятие сорвалось по вине преподавателя.

    Ученикам при этом проставляется 'cancelled', а не пропуск:
    они не виноваты, что занятия не было.
    """
    lesson = await lesson_service.get_lesson(lesson_id)
    _assert_lesson_access(current_user, lesson.teacher_id)

    lesson = await lesson_service.mark_as_teacher_missed(lesson_id)
    return await _build_response(lesson, lesson_service)

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
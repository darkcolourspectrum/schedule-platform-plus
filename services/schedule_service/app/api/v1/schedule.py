from typing import List, Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import (
    get_current_teacher,
    get_current_student,
    get_current_admin,
    get_schedule_service,
    CurrentUser
)
from app.services.schedule_service import ScheduleService
from app.models.lesson import LessonType
from app.core.exceptions import ValidationException

router = APIRouter(prefix="/schedule", tags=["Schedule"])


# === Pydantic схемы для запросов и ответов ===

class TimeSlotReservationRequest(BaseModel):
    """Запрос на резервирование временного слота"""
    slot_id: int = Field(..., description="ID временного слота")


class LessonCreateRequest(BaseModel):
    """Запрос на создание урока в слоте"""
    slot_id: int = Field(..., description="ID забронированного слота")
    title: str = Field(..., min_length=1, max_length=200, description="Название урока")
    lesson_type: LessonType = Field(LessonType.INDIVIDUAL, description="Тип урока")
    description: Optional[str] = Field(None, max_length=1000, description="Описание урока")
    max_students: int = Field(1, ge=1, le=10, description="Максимальное количество учеников")


class StudentEnrollmentRequest(BaseModel):
    """Запрос на запись ученика на урок"""
    student_id: int = Field(..., description="ID ученика из Auth Service")
    student_name: str = Field(..., min_length=1, max_length=200, description="Имя ученика")
    student_email: str = Field(..., description="Email ученика")
    student_phone: Optional[str] = Field(None, description="Телефон ученика")
    student_level: str = Field("beginner", description="Уровень ученика")


class LessonCancellationRequest(BaseModel):
    """Запрос на отмену урока"""
    reason: str = Field(..., min_length=1, max_length=500, description="Причина отмены")


# === Endpoints для преподавателей ===

@router.get(
    "/teacher/my-schedule",
    summary="Расписание преподавателя",
    description="Получение расписания текущего преподавателя"
)
async def get_teacher_schedule(
    start_date: date = Query(..., description="Дата начала периода"),
    end_date: date = Query(..., description="Дата окончания периода"),
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение расписания преподавателя"""
    
    # Ограничиваем диапазон запроса (максимум 4 недели)
    if (end_date - start_date).days > 28:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 4 weeks"
        )
    
    return await schedule_service.get_teacher_schedule(
        teacher_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )


@router.post(
    "/teacher/reserve-slot",
    summary="Резервирование временного слота",
    description="Бронирование слота преподавателем для последующего создания урока"
)
async def reserve_time_slot(
    request: TimeSlotReservationRequest,
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Резервирование слота преподавателем"""
    
    reserved_slot = await schedule_service.reserve_time_slot(
        teacher_id=current_user.id,
        teacher_name=current_user.full_name,
        teacher_email=current_user.email,
        slot_id=request.slot_id
    )
    
    return {
        "message": "Time slot reserved successfully",
        "slot": {
            "id": reserved_slot.id,
            "date": reserved_slot.date.isoformat(),
            "time_range": reserved_slot.time_range_str,
            "studio_name": reserved_slot.studio.name,
            "room_name": reserved_slot.room.name,
            "status": reserved_slot.status.value
        }
    }


@router.delete(
    "/teacher/cancel-reservation/{slot_id}",
    summary="Отмена резервирования слота",
    description="Снятие брони со временного слота"
)
async def cancel_slot_reservation(
    slot_id: int = Path(..., description="ID временного слота"),
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Отмена резервирования слота"""
    
    success = await schedule_service.cancel_time_slot_reservation(
        teacher_id=current_user.id,
        slot_id=slot_id
    )
    
    if success:
        return {"message": "Slot reservation cancelled successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel reservation at this time"
        )


@router.post(
    "/teacher/create-lesson",
    summary="Создание урока в слоте",
    description="Создание урока в забронированном временном слоте"
)
async def create_lesson(
    request: LessonCreateRequest,
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Создание урока в забронированном слоте"""
    
    lesson = await schedule_service.create_lesson_in_slot(
        teacher_id=current_user.id,
        teacher_name=current_user.full_name,
        teacher_email=current_user.email,
        slot_id=request.slot_id,
        title=request.title,
        lesson_type=request.lesson_type,
        description=request.description,
        max_students=request.max_students
    )
    
    return {
        "message": "Lesson created successfully",
        "lesson": {
            "id": lesson.id,
            "title": lesson.title,
            "type": lesson.lesson_type.value,
            "date": lesson.date_str,
            "time_range": lesson.time_range_str,
            "studio_name": lesson.studio_name,
            "room_name": lesson.room_name,
            "max_students": lesson.max_students,
            "status": lesson.status.value
        }
    }


@router.post(
    "/teacher/lessons/{lesson_id}/enroll-student",
    summary="Запись ученика на урок",
    description="Добавление ученика к уроку преподавателем"
)
async def enroll_student_to_lesson(
    lesson_id: int = Path(..., description="ID урока"),
    request: StudentEnrollmentRequest = ...,
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Запись ученика на урок"""
    
    success = await schedule_service.enroll_student_to_lesson(
        lesson_id=lesson_id,
        teacher_id=current_user.id,
        student_id=request.student_id,
        student_name=request.student_name,
        student_email=request.student_email,
        student_phone=request.student_phone,
        student_level=request.student_level
    )
    
    if success:
        return {"message": "Student enrolled successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot enroll student to this lesson"
        )


@router.delete(
    "/teacher/lessons/{lesson_id}/students/{student_id}",
    summary="Удаление ученика с урока",
    description="Снятие ученика с записи на урок"
)
async def remove_student_from_lesson(
    lesson_id: int = Path(..., description="ID урока"),
    student_id: int = Path(..., description="ID ученика"),
    current_user: CurrentUser = Depends(get_current_teacher),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Удаление ученика с урока"""
    
    success = await schedule_service.remove_student_from_lesson(
        lesson_id=lesson_id,
        teacher_id=current_user.id,
        student_id=student_id
    )
    
    if success:
        return {"message": "Student removed from lesson"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove student from lesson"
        )


# === Endpoints для учеников ===

@router.get(
    "/student/my-schedule",
    summary="Расписание ученика",
    description="Получение расписания текущего ученика"
)
async def get_student_schedule(
    start_date: date = Query(..., description="Дата начала периода"),
    end_date: date = Query(..., description="Дата окончания периода"),
    current_user: CurrentUser = Depends(get_current_student),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение расписания ученика"""
    
    # Ограничиваем диапазон (ученикам достаточно 2 недель)
    if (end_date - start_date).days > 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 2 weeks"
        )
    
    return await schedule_service.get_student_schedule(
        student_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )


@router.post(
    "/student/lessons/{lesson_id}/cancel",
    summary="Отмена урока учеником",
    description="Снятие с записи на урок (или полная отмена при индивидуальном уроке)"
)
async def cancel_lesson_by_student(
    lesson_id: int = Path(..., description="ID урока"),
    request: LessonCancellationRequest = ...,
    current_user: CurrentUser = Depends(get_current_student),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Отмена урока учеником"""
    
    success = await schedule_service.cancel_lesson_by_student(
        lesson_id=lesson_id,
        student_id=current_user.id,
        reason=request.reason
    )
    
    if success:
        return {"message": "Lesson cancelled successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel lesson at this time"
        )


# === Общие endpoints ===

@router.get(
    "/available-slots",
    summary="Доступные слоты для бронирования",
    description="Получение свободных временных слотов"
)
async def get_available_slots(
    studio_id: int = Query(..., description="ID студии"),
    start_date: date = Query(..., description="Дата начала поиска"),
    end_date: date = Query(..., description="Дата окончания поиска"),
    room_type: Optional[str] = Query(None, description="Тип кабинета"),
    min_capacity: int = Query(1, ge=1, description="Минимальная вместимость"),
    current_user: CurrentUser = Depends(get_current_teacher),  # Только преподаватели могут бронировать
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение доступных слотов для бронирования"""
    
    # Проверяем доступ к студии
    if not current_user.has_studio_access(studio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this studio"
        )
    
    # Ограничиваем поиск 2 неделями
    if (end_date - start_date).days > 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search period cannot exceed 2 weeks"
        )
    
    available_slots = await schedule_service.get_available_slots_for_booking(
        studio_id=studio_id,
        start_date=start_date,
        end_date=end_date,
        room_type=room_type,
        min_capacity=min_capacity
    )
    
    return {
        "studio_id": studio_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "total_slots": len(available_slots),
        "available_slots": available_slots
    }
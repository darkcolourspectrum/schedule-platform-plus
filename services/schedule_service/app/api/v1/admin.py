from typing import List, Optional
from datetime import date, time
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import get_current_admin, get_schedule_service, CurrentUser
from app.services.schedule_service import ScheduleService
from app.models.room import RoomType

router = APIRouter(prefix="/admin", tags=["Admin"])


# === Pydantic схемы ===

class StudioScheduleSettingsUpdate(BaseModel):
    """Обновление настроек расписания студии"""
    working_hours_start: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    working_hours_end: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    slot_duration_minutes: Optional[int] = Field(None, ge=15, le=180)


class SlotGenerationRequest(BaseModel):
    """Запрос на генерацию временных слотов"""
    studio_id: int = Field(..., description="ID студии")
    start_date: date = Field(..., description="Дата начала генерации (понедельник)")
    room_ids: Optional[List[int]] = Field(None, description="ID кабинетов (если не указано - все активные)")
    slot_duration_minutes: Optional[int] = Field(None, ge=30, le=120, description="Длительность слота")


class SlotBlockRequest(BaseModel):
    """Запрос на блокировку слота"""
    reason: str = Field(..., min_length=1, max_length=500, description="Причина блокировки")


class RoomCreateRequest(BaseModel):
    """Создание нового кабинета"""
    studio_id: int = Field(..., description="ID студии")
    name: str = Field(..., min_length=1, max_length=100, description="Название кабинета")
    room_type: RoomType = Field(RoomType.VOCAL_SMALL, description="Тип кабинета")
    description: Optional[str] = Field(None, max_length=500, description="Описание")
    max_capacity: int = Field(2, ge=1, le=20, description="Максимальная вместимость")
    has_piano: bool = Field(True, description="Наличие фортепиано")
    has_microphone: bool = Field(True, description="Наличие микрофона")
    has_mirror: bool = Field(True, description="Наличие зеркал")
    has_sound_system: bool = Field(True, description="Наличие звуковой системы")
    has_recording_equipment: bool = Field(False, description="Наличие оборудования для записи")
    area_sqm: Optional[int] = Field(None, ge=1, description="Площадь в кв.м")
    floor_number: Optional[int] = Field(1, ge=1, description="Этаж")


# === Управление студиями ===

@router.get(
    "/studios/{studio_id}/schedule",
    summary="Полное расписание студии",
    description="Получение расписания студии на конкретный день со всеми деталями"
)
async def get_studio_full_schedule(
    studio_id: int = Path(..., description="ID студии"),
    target_date: date = Query(..., description="Дата для просмотра расписания"),
    room_id: Optional[int] = Query(None, description="ID конкретного кабинета"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение полного расписания студии на день"""
    
    return await schedule_service.get_studio_schedule(
        studio_id=studio_id,
        target_date=target_date,
        room_id=room_id
    )


@router.put(
    "/studios/{studio_id}/schedule-settings",
    summary="Настройки расписания студии",
    description="Обновление рабочих часов и настроек слотов"
)
async def update_studio_schedule_settings(
    studio_id: int = Path(..., description="ID студии"),
    settings: StudioScheduleSettingsUpdate = ...,
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Обновление настроек расписания студии"""
    
    from app.repositories.studio_repository import StudioRepository
    
    studio_repo = StudioRepository(schedule_service.db)
    
    updated_studio = await studio_repo.update_schedule_settings(
        studio_id=studio_id,
        working_hours_start=settings.working_hours_start,
        working_hours_end=settings.working_hours_end,
        slot_duration_minutes=settings.slot_duration_minutes
    )
    
    if not updated_studio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio not found"
        )
    
    return {
        "message": "Schedule settings updated successfully",
        "studio": {
            "id": updated_studio.id,
            "name": updated_studio.name,
            "working_hours": updated_studio.working_hours_range,
            "slot_duration_minutes": updated_studio.slot_duration_minutes
        }
    }


# === Управление временными слотами ===

@router.post(
    "/generate-slots",
    summary="Генерация временных слотов",
    description="Автоматическая генерация слотов на неделю для студии"
)
async def generate_time_slots(
    request: SlotGenerationRequest,
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Генерация временных слотов на неделю"""
    
    # Проверяем, что start_date - понедельник
    if request.start_date.weekday() != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be a Monday"
        )
    
    created_slots = await schedule_service.generate_time_slots_for_studio(
        studio_id=request.studio_id,
        start_date=request.start_date,
        room_ids=request.room_ids,
        slot_duration_minutes=request.slot_duration_minutes
    )
    
    return {
        "message": f"Generated {len(created_slots)} time slots successfully",
        "studio_id": request.studio_id,
        "week_start": request.start_date.isoformat(),
        "total_slots": len(created_slots),
        "slots_per_day": len(created_slots) // 7 if created_slots else 0
    }


@router.post(
    "/slots/{slot_id}/block",
    summary="Блокировка временного слота",
    description="Блокировка слота администратором для обслуживания или других нужд"
)
async def block_time_slot(
    slot_id: int = Path(..., description="ID временного слота"),
    request: SlotBlockRequest = ...,
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Блокировка временного слота"""
    
    blocked_slot = await schedule_service.block_time_slot(
        slot_id=slot_id,
        reason=request.reason
    )
    
    return {
        "message": "Time slot blocked successfully",
        "slot": {
            "id": blocked_slot.id,
            "date": blocked_slot.date.isoformat(),
            "time_range": blocked_slot.time_range_str,
            "status": blocked_slot.status.value,
            "reason": blocked_slot.admin_notes
        }
    }


@router.delete(
    "/slots/{slot_id}/unblock",
    summary="Разблокировка временного слота",
    description="Снятие блокировки со слота"
)
async def unblock_time_slot(
    slot_id: int = Path(..., description="ID временного слота"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Разблокировка временного слота"""
    
    slot = await schedule_service.time_slot_repo.get_by_id(slot_id)
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time slot not found"
        )
    
    slot.unblock_slot()
    await schedule_service.db.commit()
    
    return {
        "message": "Time slot unblocked successfully",
        "slot": {
            "id": slot.id,
            "date": slot.date.isoformat(),
            "time_range": f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}",
            "status": slot.status.value
        }
    }


# === Управление кабинетами ===

@router.get(
    "/studios/{studio_id}/rooms",
    summary="Список кабинетов студии",
    description="Получение всех кабинетов студии с детальной информацией"
)
async def get_studio_rooms(
    studio_id: int = Path(..., description="ID студии"),
    include_inactive: bool = Query(False, description="Включить неактивные кабинеты"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение кабинетов студии"""
    
    from app.repositories.room_repository import RoomRepository
    room_repo = RoomRepository(schedule_service.db)
    
    rooms = await room_repo.get_studio_rooms(
        studio_id=studio_id,
        active_only=not include_inactive
    )
    
    return {
        "studio_id": studio_id,
        "total_rooms": len(rooms),
        "rooms": [
            {
                "id": room.id,
                "name": room.name,
                "type": room.room_type.value,
                "description": room.description,
                "max_capacity": room.max_capacity,
                "area_sqm": room.area_sqm,
                "floor_number": room.floor_number,
                "equipment": room.equipment_list,
                "is_active": room.is_active,
                "equipment_details": {
                    "has_piano": room.has_piano,
                    "has_microphone": room.has_microphone,
                    "has_mirror": room.has_mirror,
                    "has_sound_system": room.has_sound_system,
                    "has_recording_equipment": room.has_recording_equipment
                }
            }
            for room in rooms
        ]
    }


@router.post(
    "/rooms",
    summary="Создание нового кабинета",
    description="Добавление кабинета в студию",
    status_code=status.HTTP_201_CREATED
)
async def create_room(
    request: RoomCreateRequest,
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Создание нового кабинета"""
    
    from app.repositories.room_repository import RoomRepository
    room_repo = RoomRepository(schedule_service.db)
    
    room = await room_repo.create_room(
        studio_id=request.studio_id,
        name=request.name,
        room_type=request.room_type,
        description=request.description,
        max_capacity=request.max_capacity,
        has_piano=request.has_piano,
        has_microphone=request.has_microphone,
        has_mirror=request.has_mirror,
        has_sound_system=request.has_sound_system,
        has_recording_equipment=request.has_recording_equipment,
        area_sqm=request.area_sqm,
        floor_number=request.floor_number
    )
    
    return {
        "message": "Room created successfully",
        "room": {
            "id": room.id,
            "name": room.name,
            "type": room.room_type.value,
            "studio_id": room.studio_id,
            "max_capacity": room.max_capacity,
            "equipment": room.equipment_list
        }
    }


@router.put(
    "/rooms/{room_id}/status",
    summary="Изменение статуса кабинета",
    description="Активация/деактивация кабинета"
)
async def update_room_status(
    room_id: int = Path(..., description="ID кабинета"),
    is_active: bool = Query(..., description="Новый статус активности"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Изменение статуса активности кабинета"""
    
    from app.repositories.room_repository import RoomRepository
    room_repo = RoomRepository(schedule_service.db)
    
    updated_room = await room_repo.update_room_status(room_id, is_active)
    
    if not updated_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    status_text = "activated" if is_active else "deactivated"
    
    return {
        "message": f"Room {status_text} successfully",
        "room_id": room_id,
        "is_active": is_active
    }


# === Статистика и аналитика ===

@router.get(
    "/statistics/lessons",
    summary="Статистика уроков",
    description="Аналитика по урокам за период"
)
async def get_lesson_statistics(
    start_date: date = Query(..., description="Начало периода"),
    end_date: date = Query(..., description="Конец периода"),
    studio_id: Optional[int] = Query(None, description="ID студии (все студии если не указано)"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение статистики по урокам"""
    
    statistics = await schedule_service.get_lesson_statistics(
        start_date=start_date,
        end_date=end_date,
        studio_id=studio_id
    )
    
    return statistics


@router.get(
    "/statistics/utilization",
    summary="Статистика использования кабинетов",
    description="Процент загруженности кабинетов за период"
)
async def get_room_utilization(
    start_date: date = Query(..., description="Начало периода"),
    end_date: date = Query(..., description="Конец периода"),
    studio_id: Optional[int] = Query(None, description="ID студии"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение статистики использования кабинетов"""
    
    utilization = await schedule_service.get_room_utilization_statistics(
        start_date=start_date,
        end_date=end_date,
        studio_id=studio_id
    )
    
    return utilization


@router.get(
    "/analytics/lessons",
    summary="Статистика по урокам",
    description="Получение статистики проведенных уроков"
)
async def get_lesson_analytics(
    studio_id: Optional[int] = Query(None, description="ID студии для фильтрации"),
    teacher_id: Optional[int] = Query(None, description="ID преподавателя для фильтрации"),
    start_date: Optional[date] = Query(None, description="Дата начала периода"),
    end_date: Optional[date] = Query(None, description="Дата окончания периода"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Получение статистики по урокам"""
    
    from app.repositories.lesson_repository import LessonRepository
    lesson_repo = LessonRepository(schedule_service.db)
    
    stats = await lesson_repo.get_lesson_statistics(
        teacher_id=teacher_id,
        studio_id=studio_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return {
        "filters": {
            "studio_id": studio_id,
            "teacher_id": teacher_id,
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        },
        "statistics": stats
    }


@router.get(
    "/analytics/utilization",
    summary="Загруженность студии",
    description="Аналитика использования кабинетов и временных слотов"
)
async def get_studio_utilization(
    studio_id: int = Query(..., description="ID студии"),
    start_date: date = Query(..., description="Дата начала периода"),
    end_date: date = Query(..., description="Дата окончания периода"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Аналитика загруженности студии"""
    
    # Проверяем разумный период (максимум месяц)
    if (end_date - start_date).days > 31:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis period cannot exceed 1 month"
        )
    
    from app.repositories.time_slot_repository import TimeSlotRepository
    time_slot_repo = TimeSlotRepository(schedule_service.db)
    
    # Получаем все слоты за период
    all_slots = await time_slot_repo.get_studio_schedule_range(
        studio_id=studio_id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Группируем по статусам
    status_counts = {}
    room_utilization = {}
    
    for slot in all_slots:
        # Подсчет по статусам
        status = slot.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Подсчет по кабинетам
        room_name = slot.room.name
        if room_name not in room_utilization:
            room_utilization[room_name] = {
                "total_slots": 0,
                "booked_slots": 0,
                "reserved_slots": 0,
                "available_slots": 0
            }
        
        room_utilization[room_name]["total_slots"] += 1
        
        if slot.status.value == "booked":
            room_utilization[room_name]["booked_slots"] += 1
        elif slot.status.value == "reserved":
            room_utilization[room_name]["reserved_slots"] += 1
        elif slot.status.value == "available":
            room_utilization[room_name]["available_slots"] += 1
    
    # Вычисляем проценты
    total_slots = len(all_slots)
    for room_data in room_utilization.values():
        if room_data["total_slots"] > 0:
            room_data["utilization_percentage"] = round(
                ((room_data["booked_slots"] + room_data["reserved_slots"]) / room_data["total_slots"]) * 100,
                1
            )
    
    return {
        "studio_id": studio_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_days": (end_date - start_date).days + 1
        },
        "overall": {
            "total_slots": total_slots,
            "status_breakdown": status_counts,
            "overall_utilization": round(
                (status_counts.get("booked", 0) + status_counts.get("reserved", 0)) / total_slots * 100, 1
            ) if total_slots > 0 else 0
        },
        "by_room": room_utilization
    }


# === Экстренные действия ===

@router.post(
    "/emergency/cancel-lesson/{lesson_id}",
    summary="Экстренная отмена урока",
    description="Принудительная отмена урока администратором"
)
async def emergency_cancel_lesson(
    lesson_id: int = Path(..., description="ID урока"),
    reason: str = Query(..., min_length=1, description="Причина отмены"),
    notify_participants: bool = Query(True, description="Уведомить участников"),
    current_user: CurrentUser = Depends(get_current_admin),
    schedule_service: ScheduleService = Depends(get_schedule_service)
):
    """Экстренная отмена урока администратором"""
    
    from app.repositories.lesson_repository import LessonRepository
    lesson_repo = LessonRepository(schedule_service.db)
    
    success = await lesson_repo.cancel_lesson(
        lesson_id=lesson_id,
        reason=f"Emergency cancellation by admin: {reason}",
        by_teacher=False,
        by_student=False
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found or cannot be cancelled"
        )
    
    # TODO: Отправить уведомления участникам если notify_participants=True
    
    return {
        "message": "Lesson cancelled successfully",
        "lesson_id": lesson_id,
        "notifications_sent": notify_participants
    }
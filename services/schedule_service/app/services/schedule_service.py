from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.time_slot_repository import TimeSlotRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.studio_repository import StudioRepository
from app.repositories.room_repository import RoomRepository
from app.models.time_slot import TimeSlot, SlotStatus
from app.models.lesson import Lesson, LessonStatus, LessonType
from app.models.studio import Studio
from app.models.room import Room
from app.core.exceptions import (
    StudioNotFoundException,
    RoomNotFoundException,
    TimeSlotConflictException,
    UnauthorizedStudioAccessException,
    LessonPermissionDeniedException,
    ValidationException
)


class ScheduleService:
    """
    Основной сервис для работы с расписанием
    Содержит всю бизнес-логику управления слотами и уроками
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.time_slot_repo = TimeSlotRepository(db)
        self.lesson_repo = LessonRepository(db)
        self.studio_repo = StudioRepository(db)
        self.room_repo = RoomRepository(db)
    
    # === Методы для преподавателей ===
    
    async def get_teacher_schedule(
        self,
        teacher_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Получение расписания преподавателя
        
        Returns:
            Dict с расписанием, включая свободные и занятые слоты
        """
        
        # Получаем забронированные слоты преподавателя
        teacher_slots = await self.time_slot_repo.get_teacher_slots(
            teacher_id=teacher_id,
            start_date=start_date,
            end_date=end_date,
            include_completed=True
        )
        
        # Получаем уроки преподавателя
        teacher_lessons = await self.lesson_repo.get_teacher_lessons(
            teacher_id=teacher_id,
            start_date=start_date,
            end_date=end_date,
            include_cancelled=True
        )
        
        # Группируем по датам для удобства отображения
        schedule_by_date = {}
        
        for slot in teacher_slots:
            date_str = slot.date.isoformat()
            if date_str not in schedule_by_date:
                schedule_by_date[date_str] = {
                    "date": date_str,
                    "slots": [],
                    "lessons": []
                }
            
            schedule_by_date[date_str]["slots"].append({
                "id": slot.id,
                "time_range": slot.time_range_str,
                "studio_name": slot.studio.name,
                "room_name": slot.room.name,
                "status": slot.status.value,
                "has_lesson": slot.lesson is not None
            })
        
        for lesson in teacher_lessons:
            date_str = lesson.date_str
            if date_str not in schedule_by_date:
                schedule_by_date[date_str] = {
                    "date": date_str,
                    "slots": [],
                    "lessons": []
                }
            
            schedule_by_date[date_str]["lessons"].append({
                "id": lesson.id,
                "title": lesson.title,
                "type": lesson.lesson_type.value,
                "status": lesson.status.value,
                "time_range": lesson.time_range_str,
                "students_count": lesson.student_count,
                "students_names": lesson.students_names,
                "studio_name": lesson.studio_name,
                "room_name": lesson.room_name
            })
        
        return {
            "teacher_id": teacher_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "schedule": list(schedule_by_date.values())
        }
    
    async def reserve_time_slot(
        self,
        teacher_id: int,
        teacher_name: str,
        teacher_email: str,
        slot_id: int
    ) -> TimeSlot:
        """Резервирование временного слота преподавателем"""
        
        success = await self.time_slot_repo.reserve_slot_for_teacher(
            slot_id=slot_id,
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            teacher_email=teacher_email
        )
        
        if not success:
            slot = await self.time_slot_repo.get_by_id(slot_id)
            if not slot:
                raise ValidationException("Time slot not found")
            elif not slot.is_available:
                raise TimeSlotConflictException(
                    room_name=slot.room.name,
                    time_info=f"{slot.date} {slot.time_range_str}"
                )
        
        return await self.time_slot_repo.get_by_id(slot_id, relationships=["studio", "room"])
    
    async def cancel_time_slot_reservation(
        self,
        teacher_id: int,
        slot_id: int
    ) -> bool:
        """Отмена резервирования временного слота"""
        
        success = await self.time_slot_repo.release_teacher_reservation(
            slot_id=slot_id,
            teacher_id=teacher_id
        )
        
        if not success:
            slot = await self.time_slot_repo.get_by_id(slot_id)
            if not slot:
                raise ValidationException("Time slot not found")
            elif not slot.can_be_cancelled_by_teacher(teacher_id):
                raise LessonPermissionDeniedException()
        
        return success
    
    async def create_lesson_in_slot(
        self,
        teacher_id: int,
        teacher_name: str,
        teacher_email: str,
        slot_id: int,
        title: str,
        lesson_type: LessonType = LessonType.INDIVIDUAL,
        description: Optional[str] = None,
        max_students: int = 1
    ) -> Lesson:
        """Создание урока в забронированном слоте"""
        
        lesson = await self.lesson_repo.create_lesson_in_slot(
            time_slot_id=slot_id,
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            teacher_email=teacher_email,
            title=title,
            lesson_type=lesson_type,
            description=description,
            max_students=max_students
        )
        
        if not lesson:
            raise ValidationException("Cannot create lesson in this slot")
        
        return lesson
    
    async def enroll_student_to_lesson(
        self,
        lesson_id: int,
        teacher_id: int,
        student_id: int,
        student_name: str,
        student_email: str,
        student_phone: str = "",
        student_level: str = "beginner"
    ) -> bool:
        """Запись ученика на урок преподавателем"""
        
        # Проверяем, что урок принадлежит этому преподавателю
        lesson = await self.lesson_repo.get_by_id(lesson_id)
        if not lesson or lesson.teacher_id != teacher_id:
            raise LessonPermissionDeniedException()
        
        return await self.lesson_repo.enroll_student_to_lesson(
            lesson_id=lesson_id,
            student_id=student_id,
            student_name=student_name,
            student_email=student_email,
            student_phone=student_phone,
            student_level=student_level
        )
    
    async def remove_student_from_lesson(
        self,
        lesson_id: int,
        teacher_id: int,
        student_id: int
    ) -> bool:
        """Удаление ученика с урока преподавателем"""
        
        # Проверяем права доступа
        lesson = await self.lesson_repo.get_by_id(lesson_id)
        if not lesson or lesson.teacher_id != teacher_id:
            raise LessonPermissionDeniedException()
        
        return await self.lesson_repo.remove_student_from_lesson(lesson_id, student_id)
    
    # === Методы для учеников ===
    
    async def get_student_schedule(
        self,
        student_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Получение расписания ученика"""
        
        student_lessons = await self.lesson_repo.get_student_lessons(
            student_id=student_id,
            start_date=start_date,
            end_date=end_date,
            include_cancelled=True
        )
        
        # Группируем по датам
        schedule_by_date = {}
        
        for lesson in student_lessons:
            date_str = lesson.date_str
            if date_str not in schedule_by_date:
                schedule_by_date[date_str] = {
                    "date": date_str,
                    "lessons": []
                }
            
            schedule_by_date[date_str]["lessons"].append({
                "id": lesson.id,
                "title": lesson.title,
                "type": lesson.lesson_type.value,
                "status": lesson.status.value,
                "time_range": lesson.time_range_str,
                "teacher_name": lesson.teacher_name,
                "studio_name": lesson.studio_name,
                "room_name": lesson.room_name,
                "is_group": lesson.is_group_lesson,
                "other_students": [name for name in lesson.students_names 
                                if name != next((s.get("name") for s in lesson.students 
                                               if s.get("id") == student_id), "")],
                "can_cancel": lesson.can_be_cancelled_by_student,
                "homework": lesson.homework if lesson.status == LessonStatus.COMPLETED else None
            })
        
        return {
            "student_id": student_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "schedule": list(schedule_by_date.values())
        }
    
    async def cancel_lesson_by_student(
        self,
        lesson_id: int,
        student_id: int,
        reason: str
    ) -> bool:
        """Отмена урока учеником (снятие с записи)"""
        
        # Проверяем, что ученик записан на этот урок
        lesson = await self.lesson_repo.get_by_id(lesson_id)
        if not lesson:
            raise ValidationException("Lesson not found")
        
        student_ids = [s.get("id") for s in lesson.students]
        if student_id not in student_ids:
            raise ValidationException("Student is not enrolled in this lesson")
        
        if not lesson.can_be_cancelled_by_student:
            raise ValidationException("Cannot cancel lesson at this time")
        
        # Если это единственный ученик - отменяем весь урок
        if len(lesson.students) == 1:
            return await self.lesson_repo.cancel_lesson(
                lesson_id=lesson_id,
                reason=f"Cancelled by student: {reason}",
                by_teacher=False,
                by_student=True
            )
        else:
            # Если групповой урок - просто убираем ученика
            return await self.lesson_repo.remove_student_from_lesson(lesson_id, student_id)
    
    # === Методы для администраторов ===
    
    async def get_studio_schedule(
        self,
        studio_id: int,
        target_date: date,
        room_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Получение полного расписания студии на день"""
        
        studio = await self.studio_repo.get_by_id(studio_id, relationships=["rooms"])
        if not studio:
            raise StudioNotFoundException(studio_id)
        
        # Получаем все слоты и уроки
        time_slots = await self.time_slot_repo.get_studio_schedule(studio_id, target_date, room_id)
        lessons = await self.lesson_repo.get_studio_lessons(studio_id, target_date, room_id)
        
        # Создаем карту уроков по слотам
        lessons_by_slot = {lesson.time_slot_id: lesson for lesson in lessons}
        
        # Группируем по кабинетам
        schedule_by_room = {}
        
        for slot in time_slots:
            room_name = slot.room.name
            if room_name not in schedule_by_room:
                schedule_by_room[room_name] = {
                    "room_id": slot.room_id,
                    "room_name": room_name,
                    "room_type": slot.room.room_type.value,
                    "slots": []
                }
            
            lesson = lessons_by_slot.get(slot.id)
            slot_data = {
                "id": slot.id,
                "time_range": slot.time_range_str,
                "status": slot.status.value,
                "reserved_by": slot.reserved_by_teacher_name,
                "lesson": None
            }
            
            if lesson:
                slot_data["lesson"] = {
                    "id": lesson.id,
                    "title": lesson.title,
                    "type": lesson.lesson_type.value,
                    "status": lesson.status.value,
                    "teacher_name": lesson.teacher_name,
                    "students_count": lesson.student_count,
                    "students_names": lesson.students_names
                }
            
            schedule_by_room[room_name]["slots"].append(slot_data)
        
        return {
            "studio": {
                "id": studio.id,
                "name": studio.name,
                "working_hours": studio.working_hours_range
            },
            "date": target_date.isoformat(),
            "rooms": list(schedule_by_room.values())
        }
    
    async def generate_time_slots_for_studio(
        self,
        studio_id: int,
        start_date: date,
        room_ids: Optional[List[int]] = None,
        slot_duration_minutes: Optional[int] = None
    ) -> List[TimeSlot]:
        """Генерация временных слотов для студии на неделю"""
        
        studio = await self.studio_repo.get_by_id(studio_id, relationships=["rooms"])
        if not studio:
            raise StudioNotFoundException(studio_id)
        
        # Определяем кабинеты
        if room_ids:
            rooms = [room for room in studio.rooms if room.id in room_ids and room.is_active]
        else:
            rooms = [room for room in studio.rooms if room.is_active]
        
        if not rooms:
            raise ValidationException("No active rooms found")
        
        # Определяем параметры слотов
        duration = slot_duration_minutes or studio.slot_duration_minutes
        start_time = time.fromisoformat(studio.working_hours_start)
        end_time = time.fromisoformat(studio.working_hours_end)
        
        # Генерируем слоты
        created_slots = await self.time_slot_repo.generate_weekly_slots(
            studio_id=studio_id,
            room_ids=[room.id for room in rooms],
            start_date=start_date,
            working_hours_start=start_time,
            working_hours_end=end_time,
            slot_duration_minutes=duration
        )
        
        return created_slots
    
    async def block_time_slot(
        self,
        slot_id: int,
        reason: str
    ) -> TimeSlot:
        """Блокировка временного слота администратором"""
        
        slot = await self.time_slot_repo.get_by_id(slot_id)
        if not slot:
            raise ValidationException("Time slot not found")
        
        slot.block_by_admin(reason)
        await self.db.commit()
        
        return slot
    
    # === Утилитарные методы ===
    
    async def get_available_slots_for_booking(
        self,
        studio_id: int,
        start_date: date,
        end_date: date,
        room_type: Optional[str] = None,
        min_capacity: int = 1
    ) -> List[Dict[str, Any]]:
        """Получение доступных для бронирования слотов с фильтрами"""
        
        # Получаем доступные слоты
        available_slots = await self.time_slot_repo.get_available_slots(
            studio_id=studio_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Фильтруем по требованиям к кабинету
        filtered_slots = []
        for slot in available_slots:
            room = slot.room
            
            # Проверяем тип кабинета
            if room_type and room.room_type.value != room_type:
                continue
            
            # Проверяем вместимость
            if room.max_capacity < min_capacity:
                continue
            
            filtered_slots.append({
                "slot_id": slot.id,
                "date": slot.date.isoformat(),
                "time_range": slot.time_range_str,
                "duration_minutes": slot.duration_minutes,
                "studio_name": slot.studio.name,
                "room": {
                    "id": room.id,
                    "name": room.name,
                    "type": room.room_type.value,
                    "capacity": room.max_capacity,
                    "equipment": room.equipment_summary
                }
            })
        
        return filtered_slots
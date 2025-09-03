from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.repositories.base import BaseRepository
from app.models.lesson import Lesson, LessonStatus, LessonType
from app.models.time_slot import TimeSlot


class LessonRepository(BaseRepository[Lesson]):
    """Репозиторий для работы с уроками"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Lesson, db)
    
    async def create_lesson_in_slot(
        self,
        time_slot_id: int,
        teacher_id: int,
        teacher_name: str,
        teacher_email: str,
        title: str,
        lesson_type: LessonType = LessonType.INDIVIDUAL,
        description: Optional[str] = None,
        max_students: int = 1
    ) -> Optional[Lesson]:
        """Создание урока в забронированном временном слоте"""
        
        # Проверяем, что слот существует и принадлежит этому преподавателю
        slot_query = select(TimeSlot).where(
            and_(
                TimeSlot.id == time_slot_id,
                TimeSlot.reserved_by_teacher_id == teacher_id
            )
        )
        result = await self.db.execute(slot_query)
        slot = result.scalar_one_or_none()
        
        if not slot:
            return None
        
        # Создаем урок
        lesson = await self.create(
            title=title,
            lesson_type=lesson_type,
            description=description,
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            teacher_email=teacher_email,
            time_slot_id=time_slot_id,
            studio_id=slot.studio_id,
            room_id=slot.room_id,
            max_students=max_students,
            students=[]
        )
        
        # Обновляем статус слота на BOOKED
        slot.mark_as_booked()
        await self.db.commit()
        
        return lesson
    
    async def get_teacher_lessons(
        self,
        teacher_id: int,
        start_date: date,
        end_date: date,
        include_cancelled: bool = False
    ) -> List[Lesson]:
        """Получение уроков преподавателя в заданном диапазоне"""
        
        statuses = [LessonStatus.SCHEDULED, LessonStatus.CONFIRMED, 
                   LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED]
        
        if include_cancelled:
            statuses.extend([LessonStatus.CANCELLED, LessonStatus.NO_SHOW])
        
        query = select(Lesson).options(
            selectinload(Lesson.time_slot).selectinload(TimeSlot.studio),
            selectinload(Lesson.time_slot).selectinload(TimeSlot.room)
        ).join(TimeSlot).where(
            and_(
                Lesson.teacher_id == teacher_id,
                TimeSlot.date >= start_date,
                TimeSlot.date <= end_date,
                Lesson.status.in_(statuses)
            )
        ).order_by(TimeSlot.date, TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_student_lessons(
        self,
        student_id: int,
        start_date: date,
        end_date: date,
        include_cancelled: bool = False
    ) -> List[Lesson]:
        """Получение уроков ученика в заданном диапазоне"""
        
        statuses = [LessonStatus.SCHEDULED, LessonStatus.CONFIRMED, 
                   LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED]
        
        if include_cancelled:
            statuses.extend([LessonStatus.CANCELLED, LessonStatus.NO_SHOW])
        
        # Используем JSONB операторы для поиска по ID ученика в массиве students
        query = select(Lesson).options(
            selectinload(Lesson.time_slot).selectinload(TimeSlot.studio),
            selectinload(Lesson.time_slot).selectinload(TimeSlot.room)
        ).join(TimeSlot).where(
            and_(
                TimeSlot.date >= start_date,
                TimeSlot.date <= end_date,
                Lesson.status.in_(statuses),
                # Проверяем наличие student_id в JSON массиве students
                func.json_extract_path_text(
                    func.json_array_elements(Lesson.students), 'id'
                ).cast(int) == student_id
            )
        ).order_by(TimeSlot.date, TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_studio_lessons(
        self,
        studio_id: int,
        target_date: date,
        room_id: Optional[int] = None
    ) -> List[Lesson]:
        """Получение всех уроков студии на конкретную дату"""
        
        query = select(Lesson).options(
            selectinload(Lesson.time_slot).selectinload(TimeSlot.room)
        ).join(TimeSlot).where(
            and_(
                Lesson.studio_id == studio_id,
                TimeSlot.date == target_date,
                Lesson.status.in_([
                    LessonStatus.SCHEDULED, LessonStatus.CONFIRMED,
                    LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED
                ])
            )
        )
        
        if room_id:
            query = query.where(Lesson.room_id == room_id)
        
        query = query.order_by(TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def enroll_student_to_lesson(
        self,
        lesson_id: int,
        student_id: int,
        student_name: str,
        student_email: str,
        student_phone: str = "",
        student_level: str = "beginner"
    ) -> bool:
        """Запись ученика на урок"""
        
        lesson = await self.get_by_id(lesson_id)
        if not lesson:
            return False
        
        success = lesson.add_student(
            student_id=student_id,
            name=student_name,
            email=student_email,
            phone=student_phone,
            level=student_level
        )
        
        if success:
            await self.db.commit()
        
        return success
    
    async def remove_student_from_lesson(
        self,
        lesson_id: int,
        student_id: int
    ) -> bool:
        """Удаление ученика с урока"""
        
        lesson = await self.get_by_id(lesson_id)
        if not lesson:
            return False
        
        success = lesson.remove_student(student_id)
        
        if success:
            await self.db.commit()
        
        return success
    
    async def cancel_lesson(
        self,
        lesson_id: int,
        reason: str,
        by_teacher: bool = True,
        by_student: bool = False
    ) -> bool:
        """Отмена урока"""
        
        lesson = await self.get_by_id(lesson_id, relationships=["time_slot"])
        if not lesson:
            return False
        
        success = lesson.cancel_lesson(reason, by_teacher, by_student)
        
        if success:
            await self.db.commit()
        
        return success
    
    async def complete_lesson(
        self,
        lesson_id: int,
        teacher_notes: Optional[str] = None,
        homework: Optional[str] = None
    ) -> bool:
        """Завершение урока преподавателем"""
        
        lesson = await self.get_by_id(lesson_id, relationships=["time_slot"])
        if not lesson:
            return False
        
        success = lesson.complete_lesson(teacher_notes or "", homework or "")
        
        if success:
            await self.db.commit()
        
        return success
    
    async def get_upcoming_lessons(
        self,
        teacher_id: Optional[int] = None,
        student_id: Optional[int] = None,
        days_ahead: int = 7
    ) -> List[Lesson]:
        """Получение предстоящих уроков"""
        
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        if teacher_id:
            return await self.get_teacher_lessons(teacher_id, start_date, end_date)
        elif student_id:
            return await self.get_student_lessons(student_id, start_date, end_date)
        else:
            return []
    
    async def get_lesson_statistics(
        self,
        teacher_id: Optional[int] = None,
        studio_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Получение статистики по урокам"""
        
        # Базовый запрос
        base_query = select(Lesson).join(TimeSlot)
        
        filters = []
        
        if teacher_id:
            filters.append(Lesson.teacher_id == teacher_id)
        
        if studio_id:
            filters.append(Lesson.studio_id == studio_id)
        
        if start_date:
            filters.append(TimeSlot.date >= start_date)
        
        if end_date:
            filters.append(TimeSlot.date <= end_date)
        
        if filters:
            base_query = base_query.where(and_(*filters))
        
        # Общее количество уроков
        total_query = select(func.count(Lesson.id)).select_from(base_query.subquery())
        total_result = await self.db.execute(total_query)
        total_lessons = total_result.scalar()
        
        # Статистика по статусам
        status_query = select(
            Lesson.status,
            func.count(Lesson.id)
        ).select_from(
            base_query.subquery()
        ).group_by(Lesson.status)
        
        status_result = await self.db.execute(status_query)
        status_stats = dict(status_result.all())
        
        # Статистика по типам уроков
        type_query = select(
            Lesson.lesson_type,
            func.count(Lesson.id)
        ).select_from(
            base_query.subquery()
        ).group_by(Lesson.lesson_type)
        
        type_result = await self.db.execute(type_query)
        type_stats = dict(type_result.all())
        
        return {
            "total_lessons": total_lessons,
            "by_status": status_stats,
            "by_type": type_stats,
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        }
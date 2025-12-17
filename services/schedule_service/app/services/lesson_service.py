"""
Сервис для работы с Lessons
"""

import logging
from typing import List, Optional
from datetime import date, time, datetime, timedelta

from app.models.lesson import Lesson
from app.repositories.lesson_repository import LessonRepository
from app.schemas.lesson import LessonCreate, LessonUpdate
from app.core.exceptions import (
    LessonNotFoundException,
    ClassroomConflictException,
    InvalidLessonStatusException
)

logger = logging.getLogger(__name__)


class LessonService:
    """Сервис для работы с занятиями"""
    
    def __init__(self, lesson_repo: LessonRepository):
        self.lesson_repo = lesson_repo
    
    async def create_lesson(self, data: LessonCreate) -> Lesson:
        """
        Создать разовое занятие
        
        Проверяет конфликты кабинета перед созданием
        """
        # Вычисляем end_time
        end_time = self._calculate_end_time(data.start_time, data.duration_minutes)
        
        # Проверяем конфликт кабинета
        if data.classroom_id:
            has_conflict = await self.lesson_repo.check_classroom_conflict(
                classroom_id=data.classroom_id,
                lesson_date=data.lesson_date,
                start_time=data.start_time,
                end_time=end_time
            )
            
            if has_conflict:
                raise ClassroomConflictException(
                    classroom_id=data.classroom_id,
                    lesson_date=str(data.lesson_date),
                    time=str(data.start_time)
                )
        
        # Создаем занятие
        lesson = Lesson(
            studio_id=data.studio_id,
            teacher_id=data.teacher_id,
            classroom_id=data.classroom_id,
            recurring_pattern_id=None,  # Разовое занятие
            lesson_date=data.lesson_date,
            start_time=data.start_time,
            end_time=end_time,
            status="scheduled",
            notes=data.notes
        )
        
        lesson = await self.lesson_repo.create(lesson)
        logger.info(f"Created lesson {lesson.id}")
        
        # Добавляем учеников
        for student_id in data.student_ids:
            await self.lesson_repo.add_student(lesson.id, student_id)
        
        return lesson
    
    async def get_lesson(self, lesson_id: int) -> Lesson:
        """Получить занятие по ID"""
        lesson = await self.lesson_repo.get_by_id_with_students(lesson_id)
        if not lesson:
            raise LessonNotFoundException(lesson_id)
        return lesson
    
    async def update_lesson(self, lesson_id: int, data: LessonUpdate) -> Lesson:
        """
        Обновить занятие
        
        Проверяет валидность изменений (например, конфликты кабинета)
        """
        lesson = await self.get_lesson(lesson_id)
        
        # Проверяем изменение статуса
        if data.status and data.status != lesson.status:
            self._validate_status_transition(lesson.status, data.status)
        
        # Обновляем поля
        if data.classroom_id is not None:
            # Проверяем конфликт при изменении кабинета
            if data.classroom_id != lesson.classroom_id:
                has_conflict = await self.lesson_repo.check_classroom_conflict(
                    classroom_id=data.classroom_id,
                    lesson_date=lesson.lesson_date,
                    start_time=lesson.start_time,
                    end_time=lesson.end_time,
                    exclude_lesson_id=lesson_id
                )
                
                if has_conflict:
                    raise ClassroomConflictException(
                        classroom_id=data.classroom_id,
                        lesson_date=str(lesson.lesson_date),
                        time=str(lesson.start_time)
                    )
            
            lesson.classroom_id = data.classroom_id
        
        if data.start_time is not None:
            lesson.start_time = data.start_time
            # Пересчитываем end_time
            lesson.end_time = self._calculate_end_time(data.start_time, 60)
        
        if data.status is not None:
            lesson.status = data.status
        
        if data.notes is not None:
            lesson.notes = data.notes
        
        if data.cancellation_reason is not None:
            lesson.cancellation_reason = data.cancellation_reason
        
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Updated lesson {lesson_id}")
        
        return lesson
    
    async def cancel_lesson(self, lesson_id: int, reason: Optional[str] = None) -> Lesson:
        """Отменить занятие"""
        lesson = await self.get_lesson(lesson_id)
        
        if lesson.status == "cancelled":
            return lesson
        
        lesson.status = "cancelled"
        if reason:
            lesson.cancellation_reason = reason
        
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Cancelled lesson {lesson_id}")
        
        return lesson
    
    async def complete_lesson(self, lesson_id: int) -> Lesson:
        """Отметить занятие как завершенное"""
        lesson = await self.get_lesson(lesson_id)
        
        lesson.status = "completed"
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Completed lesson {lesson_id}")
        
        return lesson
    
    async def mark_as_missed(self, lesson_id: int) -> Lesson:
        """Отметить занятие как пропущенное"""
        lesson = await self.get_lesson(lesson_id)
        
        lesson.status = "missed"
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Marked lesson {lesson_id} as missed")
        
        return lesson
    
    async def delete_lesson(self, lesson_id: int) -> bool:
        """Удалить занятие"""
        lesson = await self.get_lesson(lesson_id)
        
        result = await self.lesson_repo.delete_by_id(lesson_id)
        
        if result:
            logger.info(f"Deleted lesson {lesson_id}")
        
        return result
    
    async def get_lessons_by_studio(
        self,
        studio_id: int,
        from_date: date,
        to_date: date
    ) -> List[Lesson]:
        """Получить все занятия студии за период"""
        return await self.lesson_repo.get_by_studio(studio_id, from_date, to_date)
    
    async def get_lessons_by_teacher(
        self,
        teacher_id: int,
        from_date: date,
        to_date: date
    ) -> List[Lesson]:
        """Получить занятия преподавателя за период"""
        return await self.lesson_repo.get_by_teacher(teacher_id, from_date, to_date)
    
    async def get_lessons_by_student(
        self,
        student_id: int,
        from_date: date,
        to_date: date
    ) -> List[Lesson]:
        """Получить занятия ученика за период"""
        return await self.lesson_repo.get_by_student(student_id, from_date, to_date)
    
    async def check_classroom_conflict(
        self,
        classroom_id: int,
        lesson_date: date,
        start_time: time,
        end_time: time,
        exclude_lesson_id: Optional[int] = None
    ) -> bool:
        """Проверить конфликт кабинета"""
        return await self.lesson_repo.check_classroom_conflict(
            classroom_id=classroom_id,
            lesson_date=lesson_date,
            start_time=start_time,
            end_time=end_time,
            exclude_lesson_id=exclude_lesson_id
        )
    
    async def get_lesson_student_ids(self, lesson_id: int) -> List[int]:
        """Получить список ID учеников занятия"""
        return await self.lesson_repo.get_student_ids(lesson_id)
    
    def _calculate_end_time(self, start_time: time, duration_minutes: int) -> time:
        """Вычислить время окончания занятия"""
        start_datetime = datetime.combine(date.today(), start_time)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        return end_datetime.time()
    
    def _validate_status_transition(self, current_status: str, new_status: str) -> None:
        """
        Валидация перехода статусов
        
        Allowed transitions:
        - scheduled -> completed, cancelled, missed
        - completed -> missed (если ученик не пришел)
        - cancelled -> scheduled (восстановление)
        """
        allowed_transitions = {
            "scheduled": ["completed", "cancelled", "missed"],
            "completed": ["missed"],
            "cancelled": ["scheduled"],
            "missed": []
        }
        
        if new_status not in allowed_transitions.get(current_status, []):
            raise InvalidLessonStatusException(current_status, new_status)

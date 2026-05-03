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

from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging import (
    record_lesson_created,
    record_lesson_cancelled,
    record_lesson_rescheduled,
)

logger = logging.getLogger(__name__)


class LessonService:
    """Сервис для работы с занятиями"""
    
    def __init__(self, lesson_repo: LessonRepository, db: AsyncSession):
        self.lesson_repo = lesson_repo
        self.db = db

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
        
        # Записываем событие в outbox.
        # Коммит произойдёт ниже по стеку (в endpoint через get_async_session) -
        # тогда и lesson, и student_ids, и outbox-запись будут в одной транзакции.
        await record_lesson_created(
            self.db,
            lesson_id=lesson.id,
            teacher_id=lesson.teacher_id,
            student_ids=list(data.student_ids),
            studio_id=lesson.studio_id,
            classroom_id=lesson.classroom_id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            end_time=lesson.end_time,
        )
        
        return lesson
        
    
    async def get_lesson(self, lesson_id: int) -> Lesson:
        """Получить занятие по ID"""
        lesson = await self.lesson_repo.get_by_id_with_students(lesson_id)
        if not lesson:
            raise LessonNotFoundException(lesson_id)
        return lesson
    
    async def update_lesson(self, lesson_id: int, data: LessonUpdate) -> Lesson:
        """
        Обновить занятие (редактирование расписания и метаданных).
        
        Если изменилась дата/время/длительность - публикует событие
        lesson.rescheduled, чтобы студентам пришло уведомление.
        Изменения только кабинета или заметок не уведомляются.
        
        Смена статуса и отмена идут через отдельные эндпоинты.
        """
        lesson = await self.get_lesson(lesson_id)
        
        # Запоминаем старые значения - для diff и события lesson.rescheduled
        old_lesson_date = lesson.lesson_date
        old_start_time = lesson.start_time
        old_end_time = lesson.end_time
        old_classroom_id = lesson.classroom_id
        
        # Вычисляем новые значения расписания (если поля переданы - берём их,
        # иначе - старые). Длительность вычисляем из старых end-start.
        new_lesson_date = data.lesson_date if data.lesson_date is not None else old_lesson_date
        new_start_time = data.start_time if data.start_time is not None else old_start_time
        
        if data.duration_minutes is not None:
            new_end_time = self._calculate_end_time(new_start_time, data.duration_minutes)
        elif data.start_time is not None:
            # Сохраняем старую длительность при сдвиге времени
            old_duration = self._duration_minutes(old_start_time, old_end_time)
            new_end_time = self._calculate_end_time(new_start_time, old_duration)
        else:
            new_end_time = old_end_time
        
        new_classroom_id = data.classroom_id if data.classroom_id is not None else old_classroom_id
        
        # Конфликт кабинета проверяем по НОВЫМ значениям (не по старым).
        schedule_or_classroom_changed = (
            new_lesson_date != old_lesson_date
            or new_start_time != old_start_time
            or new_end_time != old_end_time
            or new_classroom_id != old_classroom_id
        )
        if new_classroom_id and schedule_or_classroom_changed:
            has_conflict = await self.lesson_repo.check_classroom_conflict(
                classroom_id=new_classroom_id,
                lesson_date=new_lesson_date,
                start_time=new_start_time,
                end_time=new_end_time,
                exclude_lesson_id=lesson_id,
            )
            if has_conflict:
                raise ClassroomConflictException(
                    classroom_id=new_classroom_id,
                    lesson_date=str(new_lesson_date),
                    time=str(new_start_time),
                )
        
        # Применяем изменения
        lesson.lesson_date = new_lesson_date
        lesson.start_time = new_start_time
        lesson.end_time = new_end_time
        lesson.classroom_id = new_classroom_id
        if data.notes is not None:
            lesson.notes = data.notes
        
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Updated lesson {lesson_id}")
        
        # Если изменилось расписание - шлём событие lesson.rescheduled.
        # Изменение только кабинета или заметок не уведомляем.
        schedule_changed = (
            lesson.lesson_date != old_lesson_date
            or lesson.start_time != old_start_time
            or lesson.end_time != old_end_time
        )
        
        if schedule_changed:
            student_ids = await self.lesson_repo.get_student_ids(lesson_id)
            await record_lesson_rescheduled(
                self.db,
                lesson_id=lesson.id,
                teacher_id=lesson.teacher_id,
                student_ids=student_ids,
                studio_id=lesson.studio_id,
                old_lesson_date=old_lesson_date,
                old_start_time=old_start_time,
                old_end_time=old_end_time,
                new_lesson_date=lesson.lesson_date,
                new_start_time=lesson.start_time,
                new_end_time=lesson.end_time,
            )
        
        return lesson
    
    async def cancel_lesson(self, lesson_id: int, reason: Optional[str] = None) -> Lesson:
        """Отменить занятие. Публикует событие lesson.cancelled."""
        lesson = await self.get_lesson(lesson_id)
        
        if lesson.status == "cancelled":
            return lesson
        
        lesson.status = "cancelled"
        if reason:
            lesson.cancellation_reason = reason
        
        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(f"Cancelled lesson {lesson_id}")
        
        # Получаем студентов до публикации события - они нужны для уведомлений
        student_ids = await self.lesson_repo.get_student_ids(lesson_id)
        
        await record_lesson_cancelled(
            self.db,
            lesson_id=lesson.id,
            teacher_id=lesson.teacher_id,
            student_ids=student_ids,
            studio_id=lesson.studio_id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            cancellation_reason=reason,
        )
        
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
    
    @staticmethod
    def _duration_minutes(start: time, end: time) -> int:
        """Длительность между двумя временами в минутах (без учёта суток)."""
        s = start.hour * 60 + start.minute
        e = end.hour * 60 + end.minute
        return e - s

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

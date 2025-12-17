"""
Сервис для работы с расписанием (просмотр и фильтрация)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date

from app.models.lesson import Lesson
from app.repositories.lesson_repository import LessonRepository
from app.repositories.user_repository import UserRepository
from app.services.lesson_generator_service import LessonGeneratorService
from app.schemas.schedule import ScheduleLessonItem

logger = logging.getLogger(__name__)


class ScheduleService:
    """Сервис для работы с расписанием"""
    
    def __init__(
        self,
        lesson_repo: LessonRepository,
        user_repo: UserRepository,
        generator_service: LessonGeneratorService
    ):
        self.lesson_repo = lesson_repo
        self.user_repo = user_repo
        self.generator_service = generator_service
    
    async def get_studio_schedule(
        self,
        studio_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """
        Получить расписание студии за период
        
        Автоматически догенерирует занятия если нужно
        """
        # Проверяем и генерируем занятия если нужно
        await self.generator_service.check_and_generate_if_needed(studio_id)
        
        # Получаем занятия
        lessons = await self.lesson_repo.get_by_studio(studio_id, from_date, to_date)
        
        # Преобразуем в ScheduleLessonItem
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items
    
    async def get_teacher_schedule(
        self,
        teacher_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """Получить расписание преподавателя за период"""
        lessons = await self.lesson_repo.get_by_teacher(teacher_id, from_date, to_date)
        
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items
    
    async def get_student_schedule(
        self,
        student_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """Получить занятия ученика за период"""
        lessons = await self.lesson_repo.get_by_student(student_id, from_date, to_date)
        
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items
    
    async def _lesson_to_schedule_item(self, lesson: Lesson) -> ScheduleLessonItem:
        """
        Преобразовать Lesson в ScheduleLessonItem с дополнительной информацией
        """
        # Получаем информацию о преподавателе
        teacher = await self.user_repo.get_by_id(lesson.teacher_id)
        teacher_name = self.user_repo.get_full_name(teacher) if teacher else "Unknown"
        
        # Получаем учеников
        student_ids = await self.lesson_repo.get_student_ids(lesson.id)
        students = await self.user_repo.get_by_ids(student_ids) if student_ids else []
        student_names = [self.user_repo.get_full_name(s) for s in students]
        
        # TODO: Получить информацию о кабинете из Admin Service
        classroom_name = f"Кабинет {lesson.classroom_id}" if lesson.classroom_id else None
        
        return ScheduleLessonItem(
            lesson_id=lesson.id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            end_time=lesson.end_time,
            status=lesson.status,
            teacher_id=lesson.teacher_id,
            teacher_name=teacher_name,
            classroom_id=lesson.classroom_id,
            classroom_name=classroom_name,
            student_ids=student_ids,
            student_names=student_names,
            is_recurring=lesson.recurring_pattern_id is not None,
            notes=lesson.notes
        )
    
    async def get_schedule_with_enrichment(
        self,
        lessons: List[Lesson],
        include_teacher_info: bool = True,
        include_student_info: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Получить расписание с обогащенной информацией
        (имена пользователей, кабинеты и т.д.)
        """
        enriched_lessons = []
        
        # Собираем все ID пользователей
        all_user_ids = set()
        if include_teacher_info:
            all_user_ids.update([lesson.teacher_id for lesson in lessons])
        
        if include_student_info:
            for lesson in lessons:
                student_ids = await self.lesson_repo.get_student_ids(lesson.id)
                all_user_ids.update(student_ids)
        
        # Загружаем всех пользователей одним запросом
        users = await self.user_repo.get_by_ids(list(all_user_ids)) if all_user_ids else []
        users_dict = {user.id: user for user in users}
        
        # Обогащаем данные
        for lesson in lessons:
            lesson_data = {
                "id": lesson.id,
                "lesson_date": lesson.lesson_date,
                "start_time": lesson.start_time,
                "end_time": lesson.end_time,
                "status": lesson.status,
                "classroom_id": lesson.classroom_id,
                "notes": lesson.notes,
                "is_recurring": lesson.recurring_pattern_id is not None
            }
            
            # Добавляем информацию о преподавателе
            if include_teacher_info and lesson.teacher_id in users_dict:
                teacher = users_dict[lesson.teacher_id]
                lesson_data["teacher"] = {
                    "id": teacher.id,
                    "name": self.user_repo.get_full_name(teacher),
                    "email": teacher.email
                }
            
            # Добавляем информацию об учениках
            if include_student_info:
                student_ids = await self.lesson_repo.get_student_ids(lesson.id)
                students_info = []
                for sid in student_ids:
                    if sid in users_dict:
                        student = users_dict[sid]
                        students_info.append({
                            "id": student.id,
                            "name": self.user_repo.get_full_name(student),
                            "email": student.email
                        })
                lesson_data["students"] = students_info
            
            enriched_lessons.append(lesson_data)
        
        return enriched_lessons

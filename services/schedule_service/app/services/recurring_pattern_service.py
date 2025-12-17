"""
Сервис для работы с Recurring Patterns
"""

import logging
from typing import List, Optional, Tuple
from datetime import date, timedelta

from app.models.recurring_pattern import RecurringPattern
from app.repositories.recurring_pattern_repository import RecurringPatternRepository
from app.repositories.lesson_repository import LessonRepository
from app.schemas.recurring_pattern import RecurringPatternCreate, RecurringPatternUpdate
from app.core.exceptions import RecurringPatternNotFoundException
from app.services.lesson_generator_service import LessonGeneratorService

logger = logging.getLogger(__name__)


class RecurringPatternService:
    """Сервис для работы с шаблонами повторяющихся занятий"""
    
    def __init__(
        self,
        pattern_repo: RecurringPatternRepository,
        lesson_repo: LessonRepository,
        generator_service: LessonGeneratorService
    ):
        self.pattern_repo = pattern_repo
        self.lesson_repo = lesson_repo
        self.generator_service = generator_service
    
    async def create_pattern(
        self,
        data: RecurringPatternCreate
    ) -> Tuple[RecurringPattern, int]:
        """
        Создать шаблон и автоматически сгенерировать занятия
        
        Returns:
            Tuple[pattern, generated_lessons_count]
        """
        # Создаем шаблон
        pattern = RecurringPattern(
            studio_id=data.studio_id,
            teacher_id=data.teacher_id,
            classroom_id=data.classroom_id,
            day_of_week=data.day_of_week,
            start_time=data.start_time,
            duration_minutes=data.duration_minutes,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            is_active=True,
            notes=data.notes
        )
        
        pattern = await self.pattern_repo.create(pattern)
        logger.info(f"Created recurring pattern {pattern.id}")
        
        # Добавляем учеников
        for student_id in data.student_ids:
            await self.pattern_repo.add_student(pattern.id, student_id)
        
        # Генерируем занятия на ближайшие недели
        until_date = date.today() + timedelta(weeks=2)
        generated, skipped, errors = await self.generator_service.generate_lessons_for_pattern(
            pattern,
            until_date
        )
        
        if errors:
            logger.warning(f"Errors during generation for pattern {pattern.id}: {errors}")
        
        logger.info(f"Generated {generated} lessons for pattern {pattern.id}")
        
        return pattern, generated
    
    async def get_pattern(self, pattern_id: int) -> RecurringPattern:
        """Получить шаблон по ID"""
        pattern = await self.pattern_repo.get_by_id_with_students(pattern_id)
        if not pattern:
            raise RecurringPatternNotFoundException(pattern_id)
        return pattern
    
    async def get_patterns_by_studio(
        self,
        studio_id: int,
        active_only: bool = True
    ) -> List[RecurringPattern]:
        """Получить все шаблоны студии"""
        return await self.pattern_repo.get_by_studio(studio_id, active_only)
    
    async def get_patterns_by_teacher(
        self,
        teacher_id: int,
        active_only: bool = True
    ) -> List[RecurringPattern]:
        """Получить все шаблоны преподавателя"""
        return await self.pattern_repo.get_by_teacher(teacher_id, active_only)
    
    async def update_pattern(
        self,
        pattern_id: int,
        data: RecurringPatternUpdate
    ) -> RecurringPattern:
        """Обновить шаблон"""
        pattern = await self.get_pattern(pattern_id)
        
        # Обновляем поля
        if data.classroom_id is not None:
            pattern.classroom_id = data.classroom_id
        if data.start_time is not None:
            pattern.start_time = data.start_time
        if data.duration_minutes is not None:
            pattern.duration_minutes = data.duration_minutes
        if data.valid_until is not None:
            pattern.valid_until = data.valid_until
        if data.is_active is not None:
            pattern.is_active = data.is_active
        if data.notes is not None:
            pattern.notes = data.notes
        
        # Обновляем учеников если указаны
        if data.student_ids is not None:
            await self.pattern_repo.update_students(pattern_id, data.student_ids)
        
        pattern = await self.pattern_repo.update_obj(pattern)
        logger.info(f"Updated recurring pattern {pattern_id}")
        
        return pattern
    
    async def delete_pattern(self, pattern_id: int) -> bool:
        """
        Удалить шаблон
        
        Примечание: Связанные занятия не удаляются (recurring_pattern_id просто станет NULL)
        """
        pattern = await self.get_pattern(pattern_id)
        
        result = await self.pattern_repo.delete_by_id(pattern_id)
        
        if result:
            logger.info(f"Deleted recurring pattern {pattern_id}")
        
        return result
    
    async def deactivate_pattern(self, pattern_id: int) -> RecurringPattern:
        """Деактивировать шаблон (мягкое удаление)"""
        pattern = await self.get_pattern(pattern_id)
        pattern.is_active = False
        
        pattern = await self.pattern_repo.update_obj(pattern)
        logger.info(f"Deactivated recurring pattern {pattern_id}")
        
        return pattern
    
    async def get_pattern_student_ids(self, pattern_id: int) -> List[int]:
        """Получить список ID учеников шаблона"""
        return await self.pattern_repo.get_student_ids(pattern_id)
    
    async def count_generated_lessons(self, pattern_id: int) -> int:
        """Подсчитать количество занятий, сгенерированных из шаблона"""
        lessons = await self.lesson_repo.get_by_pattern(pattern_id)
        return len(lessons)

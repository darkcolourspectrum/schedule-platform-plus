"""
Сервис генерации занятий из recurring patterns
"""

import logging
from typing import List, Optional, Tuple
from datetime import date, time, timedelta, datetime
import pytz

from app.models.recurring_pattern import RecurringPattern
from app.models.lesson import Lesson
from app.repositories.recurring_pattern_repository import RecurringPatternRepository
from app.repositories.lesson_repository import LessonRepository
from app.config import settings
from app.core.exceptions import GenerationException

logger = logging.getLogger(__name__)


class LessonGeneratorService:
    """Сервис для генерации занятий из шаблонов"""
    
    def __init__(
        self,
        pattern_repo: RecurringPatternRepository,
        lesson_repo: LessonRepository
    ):
        self.pattern_repo = pattern_repo
        self.lesson_repo = lesson_repo
        self.timezone = pytz.timezone(settings.schedule_timezone)
    
    async def generate_lessons_for_pattern(
        self,
        pattern: RecurringPattern,
        until_date: date
    ) -> Tuple[int, int, List[str]]:
        """
        Генерация занятий для конкретного шаблона
        
        Args:
            pattern: Шаблон повторения
            until_date: До какой даты генерировать
            
        Returns:
            Tuple[generated_count, skipped_count, errors]
        """
        generated_count = 0
        skipped_count = 0
        errors = []
        
        try:
            # Находим последнее сгенерированное занятие
            last_lesson = await self.lesson_repo.get_last_generated_lesson(pattern.id)
            
            if last_lesson:
                # Начинаем со следующей недели после последнего занятия
                next_date = last_lesson.lesson_date + timedelta(days=7)
            else:
                # Первая генерация - начинаем с valid_from
                next_date = pattern.valid_from
                # Находим ближайший нужный день недели
                while next_date.isoweekday() != pattern.day_of_week:
                    next_date += timedelta(days=1)
            
            # Генерируем занятия
            while next_date <= until_date:
                # Проверяем, не вышли ли за пределы valid_until
                if pattern.valid_until and next_date > pattern.valid_until:
                    break
                
                # Вычисляем end_time
                end_time = self._calculate_end_time(
                    pattern.start_time,
                    pattern.duration_minutes
                )
                
                # Проверяем конфликт кабинета
                if pattern.classroom_id:
                    has_conflict = await self.lesson_repo.check_classroom_conflict(
                        classroom_id=pattern.classroom_id,
                        lesson_date=next_date,
                        start_time=pattern.start_time,
                        end_time=end_time
                    )
                    
                    if has_conflict:
                        error_msg = f"Conflict for {next_date} at {pattern.start_time} in classroom {pattern.classroom_id}"
                        logger.warning(error_msg)
                        errors.append(error_msg)
                        skipped_count += 1
                        next_date += timedelta(days=7)
                        continue
                
                # Создаем занятие
                lesson = Lesson(
                    studio_id=pattern.studio_id,
                    teacher_id=pattern.teacher_id,
                    classroom_id=pattern.classroom_id,
                    recurring_pattern_id=pattern.id,
                    lesson_date=next_date,
                    start_time=pattern.start_time,
                    end_time=end_time,
                    status="scheduled"
                )
                
                await self.lesson_repo.create(lesson)
                
                # Копируем учеников из шаблона
                student_ids = await self.pattern_repo.get_student_ids(pattern.id)
                for student_id in student_ids:
                    await self.lesson_repo.add_student(lesson.id, student_id)
                
                generated_count += 1
                logger.info(f"Generated lesson for pattern {pattern.id} on {next_date}")
                
                # Переходим к следующей неделе
                next_date += timedelta(days=7)
            
            return generated_count, skipped_count, errors
            
        except Exception as e:
            logger.error(f"Error generating lessons for pattern {pattern.id}: {e}")
            raise GenerationException(
                message=f"Failed to generate lessons for pattern {pattern.id}",
                details=str(e)
            )
    
    async def generate_all_patterns(
        self,
        until_date: Optional[date] = None
    ) -> Tuple[int, int, List[str]]:
        """
        Генерация занятий для всех активных шаблонов
        
        Args:
            until_date: До какой даты генерировать (по умолчанию +2 недели)
            
        Returns:
            Tuple[total_generated, total_skipped, errors]
        """
        if not until_date:
            until_date = date.today() + timedelta(weeks=settings.schedule_generation_weeks)
        
        total_generated = 0
        total_skipped = 0
        all_errors = []
        
        # Получаем все активные шаблоны
        patterns = await self.pattern_repo.get_active_patterns()
        
        logger.info(f"Generating lessons for {len(patterns)} patterns until {until_date}")
        
        for pattern in patterns:
            try:
                generated, skipped, errors = await self.generate_lessons_for_pattern(
                    pattern,
                    until_date
                )
                total_generated += generated
                total_skipped += skipped
                all_errors.extend(errors)
                
            except Exception as e:
                error_msg = f"Failed to generate for pattern {pattern.id}: {str(e)}"
                logger.error(error_msg)
                all_errors.append(error_msg)
        
        logger.info(
            f"Generation complete: {total_generated} generated, "
            f"{total_skipped} skipped, {len(all_errors)} errors"
        )
        
        return total_generated, total_skipped, all_errors
    
    async def check_and_generate_if_needed(self, studio_id: int) -> Tuple[int, int]:
        """
        Проверить нужно ли генерировать занятия для студии и сгенерировать
        
        Вызывается при запросе расписания как fallback механизм
        
        Returns:
            Tuple[generated_count, skipped_count]
        """
        target_date = date.today() + timedelta(weeks=settings.schedule_generation_weeks)
        
        # Получаем активные шаблоны студии
        patterns = await self.pattern_repo.get_by_studio(studio_id, active_only=True)
        
        total_generated = 0
        total_skipped = 0
        
        for pattern in patterns:
            # Проверяем последнее сгенерированное занятие
            last_lesson = await self.lesson_repo.get_last_generated_lesson(pattern.id)
            
            if not last_lesson or last_lesson.lesson_date < target_date:
                # Нужна генерация
                generated, skipped, _ = await self.generate_lessons_for_pattern(
                    pattern,
                    target_date
                )
                total_generated += generated
                total_skipped += skipped
        
        return total_generated, total_skipped
    
    def _calculate_end_time(self, start_time: time, duration_minutes: int) -> time:
        """Вычислить время окончания занятия"""
        start_datetime = datetime.combine(date.today(), start_time)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        return end_datetime.time()

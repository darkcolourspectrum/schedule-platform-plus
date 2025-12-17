"""
Repository для работы с Lessons
"""

import logging
from typing import List, Optional
from datetime import date, time
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.lesson import Lesson
from app.models.lesson_student import LessonStudent
from app.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class LessonRepository(BaseRepository[Lesson]):
    """Repository для Lessons"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Lesson, db)
    
    async def get_by_id_with_students(self, lesson_id: int) -> Optional[Lesson]:
        """Получить занятие с загруженными учениками"""
        result = await self.db.execute(
            select(Lesson)
            .options(selectinload(Lesson.students))
            .where(Lesson.id == lesson_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_studio(
        self,
        studio_id: int,
        from_date: date,
        to_date: date,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Lesson]:
        """Получить занятия студии за период"""
        query = select(Lesson).where(
            and_(
                Lesson.studio_id == studio_id,
                Lesson.lesson_date >= from_date,
                Lesson.lesson_date <= to_date
            )
        ).order_by(Lesson.lesson_date, Lesson.start_time)
        
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_by_teacher(
        self,
        teacher_id: int,
        from_date: date,
        to_date: date
    ) -> List[Lesson]:
        """Получить занятия преподавателя за период"""
        result = await self.db.execute(
            select(Lesson).where(
                and_(
                    Lesson.teacher_id == teacher_id,
                    Lesson.lesson_date >= from_date,
                    Lesson.lesson_date <= to_date
                )
            ).order_by(Lesson.lesson_date, Lesson.start_time)
        )
        return list(result.scalars().all())
    
    async def get_by_student(
        self,
        student_id: int,
        from_date: date,
        to_date: date
    ) -> List[Lesson]:
        """Получить занятия ученика за период"""
        result = await self.db.execute(
            select(Lesson)
            .join(LessonStudent)
            .where(
                and_(
                    LessonStudent.student_id == student_id,
                    Lesson.lesson_date >= from_date,
                    Lesson.lesson_date <= to_date
                )
            )
            .order_by(Lesson.lesson_date, Lesson.start_time)
        )
        return list(result.scalars().all())
    
    async def get_by_classroom(
        self,
        classroom_id: int,
        lesson_date: date,
        exclude_lesson_id: Optional[int] = None
    ) -> List[Lesson]:
        """Получить все занятия в кабинете на определенную дату"""
        query = select(Lesson).where(
            and_(
                Lesson.classroom_id == classroom_id,
                Lesson.lesson_date == lesson_date,
                Lesson.status != "cancelled"
            )
        )
        
        if exclude_lesson_id:
            query = query.where(Lesson.id != exclude_lesson_id)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def check_classroom_conflict(
        self,
        classroom_id: int,
        lesson_date: date,
        start_time: time,
        end_time: time,
        exclude_lesson_id: Optional[int] = None
    ) -> bool:
        """
        Проверить конфликт кабинета
        
        Returns:
            True если есть конфликт, False если нет
        """
        lessons = await self.get_by_classroom(classroom_id, lesson_date, exclude_lesson_id)
        
        for lesson in lessons:
            # Проверяем пересечение временных интервалов
            if (start_time < lesson.end_time and end_time > lesson.start_time):
                return True
        
        return False
    
    async def get_by_pattern(
        self,
        pattern_id: int,
        from_date: Optional[date] = None
    ) -> List[Lesson]:
        """Получить все занятия сгенерированные из шаблона"""
        query = select(Lesson).where(
            Lesson.recurring_pattern_id == pattern_id
        )
        
        if from_date:
            query = query.where(Lesson.lesson_date >= from_date)
        
        query = query.order_by(Lesson.lesson_date)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_last_generated_lesson(self, pattern_id: int) -> Optional[Lesson]:
        """Получить последнее сгенерированное занятие из шаблона"""
        result = await self.db.execute(
            select(Lesson)
            .where(Lesson.recurring_pattern_id == pattern_id)
            .order_by(Lesson.lesson_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def add_student(self, lesson_id: int, student_id: int) -> LessonStudent:
        """Добавить ученика к занятию"""
        lesson_student = LessonStudent(
            lesson_id=lesson_id,
            student_id=student_id
        )
        self.db.add(lesson_student)
        await self.db.flush()
        return lesson_student
    
    async def remove_student(self, lesson_id: int, student_id: int) -> bool:
        """Удалить ученика из занятия"""
        from sqlalchemy import delete
        
        result = await self.db.execute(
            delete(LessonStudent).where(
                and_(
                    LessonStudent.lesson_id == lesson_id,
                    LessonStudent.student_id == student_id
                )
            )
        )
        return result.rowcount > 0
    
    async def get_student_ids(self, lesson_id: int) -> List[int]:
        """Получить список ID учеников занятия"""
        result = await self.db.execute(
            select(LessonStudent.student_id).where(
                LessonStudent.lesson_id == lesson_id
            )
        )
        return list(result.scalars().all())
    
    async def count_by_studio(
        self,
        studio_id: int,
        from_date: date,
        to_date: date
    ) -> int:
        """Подсчитать количество занятий студии за период"""
        from sqlalchemy import func
        
        result = await self.db.execute(
            select(func.count(Lesson.id)).where(
                and_(
                    Lesson.studio_id == studio_id,
                    Lesson.lesson_date >= from_date,
                    Lesson.lesson_date <= to_date
                )
            )
        )
        return result.scalar_one()

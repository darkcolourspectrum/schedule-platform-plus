"""
Repository для работы с Recurring Patterns
"""

import logging
from typing import List, Optional
from datetime import date
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.recurring_pattern import RecurringPattern
from app.models.lesson_student import RecurringPatternStudent
from app.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class RecurringPatternRepository(BaseRepository[RecurringPattern]):
    """Repository для Recurring Patterns"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(RecurringPattern, db)
    
    async def get_by_id_with_students(self, pattern_id: int) -> Optional[RecurringPattern]:
        """Получить шаблон с загруженными учениками"""
        result = await self.db.execute(
            select(RecurringPattern)
            .options(selectinload(RecurringPattern.students))
            .where(RecurringPattern.id == pattern_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_studio(
        self,
        studio_id: int,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[RecurringPattern]:
        """Получить все шаблоны студии"""
        query = select(RecurringPattern).where(
            RecurringPattern.studio_id == studio_id
        )
        
        if active_only:
            query = query.where(RecurringPattern.is_active == True)
        
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_by_teacher(
        self,
        teacher_id: int,
        active_only: bool = True
    ) -> List[RecurringPattern]:
        """Получить все шаблоны преподавателя"""
        query = select(RecurringPattern).where(
            RecurringPattern.teacher_id == teacher_id
        )
        
        if active_only:
            query = query.where(RecurringPattern.is_active == True)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_active_patterns(
        self,
        as_of_date: Optional[date] = None
    ) -> List[RecurringPattern]:
        """
        Получить все активные шаблоны на определенную дату
        
        Args:
            as_of_date: Дата для проверки (по умолчанию - сегодня)
        """
        if not as_of_date:
            from datetime import date as dt_date
            as_of_date = dt_date.today()
        
        query = select(RecurringPattern).where(
            and_(
                RecurringPattern.is_active == True,
                RecurringPattern.valid_from <= as_of_date,
                or_(
                    RecurringPattern.valid_until.is_(None),
                    RecurringPattern.valid_until >= as_of_date
                )
            )
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def add_student(self, pattern_id: int, student_id: int) -> RecurringPatternStudent:
        """Добавить ученика к шаблону"""
        pattern_student = RecurringPatternStudent(
            recurring_pattern_id=pattern_id,
            student_id=student_id
        )
        self.db.add(pattern_student)
        await self.db.flush()
        return pattern_student
    
    async def remove_student(self, pattern_id: int, student_id: int) -> bool:
        """Удалить ученика из шаблона"""
        from sqlalchemy import delete
        
        result = await self.db.execute(
            delete(RecurringPatternStudent).where(
                and_(
                    RecurringPatternStudent.recurring_pattern_id == pattern_id,
                    RecurringPatternStudent.student_id == student_id
                )
            )
        )
        return result.rowcount > 0
    
    async def get_student_ids(self, pattern_id: int) -> List[int]:
        """Получить список ID учеников шаблона"""
        result = await self.db.execute(
            select(RecurringPatternStudent.student_id).where(
                RecurringPatternStudent.recurring_pattern_id == pattern_id
            )
        )
        return list(result.scalars().all())
    
    async def update_students(self, pattern_id: int, student_ids: List[int]) -> None:
        """
        Обновить список учеников шаблона
        (удаляет старых и добавляет новых)
        """
        # Удаляем всех текущих учеников
        from sqlalchemy import delete
        await self.db.execute(
            delete(RecurringPatternStudent).where(
                RecurringPatternStudent.recurring_pattern_id == pattern_id
            )
        )
        
        # Добавляем новых
        for student_id in student_ids:
            await self.add_student(pattern_id, student_id)

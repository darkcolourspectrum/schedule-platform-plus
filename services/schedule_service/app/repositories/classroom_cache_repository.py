"""
Repository для чтения кабинетов из локального кеша Schedule Service.

Источник данных: таблица classrooms_cache, синхронизируемая из Admin Service
через consumer событий 'admin_events'.

Все методы READ-ONLY.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classroom_cache import ClassroomCache


class ClassroomCacheRepository:
    """Repository для чтения кабинетов из локального кеша."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, classroom_id: int) -> Optional[ClassroomCache]:
        """Получить кабинет по ID (включая неактивные)."""
        result = await self.db.execute(
            select(ClassroomCache).where(ClassroomCache.id == classroom_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_studio(
        self,
        studio_id: int,
        active_only: bool = True,
    ) -> List[ClassroomCache]:
        """Получить кабинеты студии."""
        stmt = select(ClassroomCache).where(
            ClassroomCache.studio_id == studio_id
        )
        if active_only:
            stmt = stmt.where(ClassroomCache.is_active.is_(True))
        stmt = stmt.order_by(ClassroomCache.name)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def exists(self, classroom_id: int) -> bool:
        """Проверить существование кабинета (включая неактивные)."""
        from sqlalchemy import exists as sql_exists
        
        result = await self.db.execute(
            select(sql_exists().where(ClassroomCache.id == classroom_id))
        )
        return bool(result.scalar())
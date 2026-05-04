"""
Repository для чтения студий из локального кеша Schedule Service.

Источник данных: таблица studios_cache, синхронизируемая из Admin Service
через consumer событий 'admin_events' (см. app/messaging/admin_consumer.py).

Все методы READ-ONLY: запись делает только consumer.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio_cache import StudioCache


class StudioCacheRepository:
    """Repository для чтения студий из локального кеша."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, studio_id: int) -> Optional[StudioCache]:
        """Получить студию по ID (включая неактивные)."""
        result = await self.db.execute(
            select(StudioCache).where(StudioCache.id == studio_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_ids(
        self,
        studio_ids: List[int],
        active_only: bool = True,
    ) -> List[StudioCache]:
        """Получить студии по списку ID."""
        if not studio_ids:
            return []
        
        stmt = select(StudioCache).where(StudioCache.id.in_(studio_ids))
        if active_only:
            stmt = stmt.where(StudioCache.is_active.is_(True))
        stmt = stmt.order_by(StudioCache.name)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_all(self, active_only: bool = True) -> List[StudioCache]:
        """Получить все студии."""
        stmt = select(StudioCache)
        if active_only:
            stmt = stmt.where(StudioCache.is_active.is_(True))
        stmt = stmt.order_by(StudioCache.name)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def exists(self, studio_id: int) -> bool:
        """Проверить существование студии (включая неактивные)."""
        from sqlalchemy import exists as sql_exists
        
        result = await self.db.execute(
            select(sql_exists().where(StudioCache.id == studio_id))
        )
        return bool(result.scalar())
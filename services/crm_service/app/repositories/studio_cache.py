"""
Репозиторий для чтения локальной копии студий (studios_cache).

studios_cache наполняется consumer'ом событий admin_events (см.
app/messaging/admin_handlers.py) и используется CRM только на чтение.

Принцип read-only: запись в эту таблицу делает только consumer.
Бизнес-логика обращается сюда для валидации studio_id при конвертации
лида и для отдачи списка студий фронту.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio_cache import StudioCache


class StudioCacheRepository:
    """Доступ на чтение к локальной копии студий."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, studio_id: int) -> Optional[StudioCache]:
        """Получить студию по id (включая неактивные)."""
        result = await self.db.execute(
            select(StudioCache).where(StudioCache.id == studio_id)
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> List[StudioCache]:
        """Получить все активные студии, отсортированные по имени."""
        result = await self.db.execute(
            select(StudioCache)
            .where(StudioCache.is_active.is_(True))
            .order_by(StudioCache.name)
        )
        return list(result.scalars().all())

    async def exists_and_active(self, studio_id: int) -> bool:
        """Проверить, что студия существует и активна."""
        studio = await self.get_by_id(studio_id)
        return studio is not None and studio.is_active